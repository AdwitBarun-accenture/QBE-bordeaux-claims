"""STAGE 05 - Classification Agent (free-text extraction)

Mockup: sent up to 4 notes to the LLM, then merged any value with confidence
>= 70 straight into the row - overwriting real fields (e.g. 'prem adj -1200'
replaced the 45,200 gross premium; 'Ded 100k' became a premium; '30d notice'
went into a date field) and matched rows by the insured's first word.

Here:
  1. Free-text sources = unmapped note/remark columns + mapped text fields
     (risk.description, claim.description).
  2. Deterministic extractors (regex) for the common bordereaux shorthand:
     endorsement dates, premium adjustments, DA limits, sub-limits, deductibles,
     reserve movements, cross-referenced claim/policy refs, coverage flags
     (BI, subrogation, general average, war, terrorism, TRIA, amended record).
  3. LLM extraction for everything else (batched, row-keyed).
  4. Every extraction has a 'kind':
       fact            -> may fill a BLANK target field if confidence >= threshold
       adjustment      -> recorded as an annotation, never overwrites amounts
       cross_reference -> recorded (links to other policies/claims)
       flag            -> coverage/claim flags, recorded
"""
import re

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.llm.base import LLMUnavailable
from app.llm.prompts import freetext as P
from app.mapping.matcher import is_free_text_column
from app.storage.factory import save_dataset
from app.utils.dates import parse_date
from app.utils.numbers import fmt_num, parse_decimal

AMT = r"([+-]?\s*\d[\d,]*(?:\.\d+)?\s*(?:k|m|bn)?)"
EXTRACTORS = [
    # (regex, field, kind, confidence, value-builder)
    (re.compile(r"\bendt\.?\s*(?:\d+\s+)?.*?(\d{1,2}/\d{1,2}/\d{2,4})", re.I), "policy.endorsement_date", "fact", 90, "date"),
    (re.compile(r"\b(?:addendum|endorsement)\s*\d*\s*(?:dt|dated)?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{2,4})", re.I), "policy.endorsement_date", "fact", 85, "date"),
    (re.compile(r"\bprem(?:ium)?\.?\s*(?:adj(?:ustment)?|uplift|increase|reduction|return)\s*" + AMT, re.I), "premium.gross_original", "adjustment", 88, "amount"),
    (re.compile(r"\bDA\s*limit\s*" + AMT, re.I), "coverholder.binding_authority", "fact", 89, "amount"),
    (re.compile(r"\bsub-?\s*limit\s*" + AMT, re.I), "risk.sum_insured", "adjustment", 77, "amount"),
    (re.compile(r"\bded(?:uctible)?\.?\s*" + AMT + r"\s*(AOO|each and every loss|EEL)?", re.I), "risk.description", "flag", 80, "deductible"),
    (re.compile(r"\b(?:reserve|res)\.?\s*(?:mvmt|movement|mvt)\s*" + AMT + r"|" + AMT + r"\s*(?:reserve|res)\.?\s*(?:mvmt|movement)", re.I), "claim.reserve_gross", "adjustment", 82, "amount"),
    (re.compile(r"\b(CLM[-/]?\d{4}[-/]?\d{3,5})\b", re.I), "claim.reference", "cross_reference", 97, "raw"),
    (re.compile(r"\b(POL[-/]?\d{4}[-/]?\d{3}[A-Z]?)\b", re.I), "policy.reference", "cross_reference", 95, "raw"),
]
FLAGS = [
    (re.compile(r"\bBI\b|business interruption", re.I), "risk.description", "Business interruption"),
    (re.compile(r"subrog", re.I), "claim.description", "Subrogation potential"),
    (re.compile(r"general average", re.I), "claim.description", "General Average declared"),
    (re.compile(r"war risk", re.I), "risk.description", "War risk extension"),
    (re.compile(r"terrorism excl", re.I), "risk.description", "Terrorism exclusion"),
    (re.compile(r"\bTRIA\b", re.I), "risk.description", "TRIA applies"),
    (re.compile(r"\b\d+\s*d(?:ays?)?\s*cancel", re.I), "risk.description", "Notice-period cancellation clause"),
    (re.compile(r"mach(?:inery)?\.?\s*b(?:reak)?d(?:o)?wn", re.I), "risk.description", "Machinery breakdown cover"),
    (re.compile(r"\bAMENDED\b|supersedes", re.I), "policy.status", "Amended record - supersedes earlier submission"),
]


def _norm(kind: str, raw: str) -> str:
    if kind == "date":
        p = parse_date(raw)
        return p.iso or raw
    if kind == "amount":
        d = parse_decimal(raw.replace(" ", ""))
        return fmt_num(d, 2) if d is not None else raw
    return raw.strip()


class ClassificationAgent(BaseAgent):
    name = "Classification Agent"

    def run(self) -> None:
        run, s = self.ctx.run, self.ctx.settings
        parsed, enriched = self.ctx.cache["parsed"], self.ctx.cache["enriched"]
        if not s["processing"]["freetext_extraction"]:
            run.freetext = {"enabled": False, "results": []}
            self.log("Free-text extraction disabled in settings")
            return
        unmapped_text_cols = [m["source"] for m in run.mappings
                              if m["status"] == "unmapped" and is_free_text_column(m["source"], [r.get(m["source"], "") for r in parsed])]
        items = []
        for i, (src, row) in enumerate(zip(parsed, enriched)):
            parts = [src.get(c, "") for c in unmapped_text_cols] + [row.get("risk.description", ""), row.get("claim.description", "")]
            text = " ".join(p for p in parts if p).strip()
            if len(text) > 20:
                items.append({"row": i + 1, "insured": row.get("insured.name", ""), "text": text})
        if not items:
            run.freetext = {"enabled": True, "results": [], "columns": unmapped_text_cols}
            self.log("No free-text content", "Nothing to extract. Stage skipped.")
            return

        results = {it["row"]: {"row": it["row"], "insured": it["insured"], "text": it["text"], "extracted": []} for it in items}
        for it in items:
            results[it["row"]]["extracted"] += self._regex(it["text"])
        self._ai(items, results)

        merged = self._merge(enriched, results, s["freetext_merge_threshold"])
        save_dataset(run.id, "enriched", enriched)  # with annotations + merges
        out = [r for r in results.values() if r["extracted"]]
        total = sum(len(r["extracted"]) for r in out)
        run.freetext = {"enabled": True, "columns": unmapped_text_cols, "results": out, "total": total, "merged": merged}
        self.log("Free-text extraction complete",
                 f"{total} structured facts from {len(items)} notes; {merged} blank field(s) filled, rest kept as annotations")

    # ------------------------------------------------------------------
    def _regex(self, text: str) -> list[dict]:
        out = []
        for rx, field, kind, conf, vk in EXTRACTORS:
            for m in rx.finditer(text):
                raw = next((g for g in m.groups() if g), "")
                value = _norm(vk if vk in ("date", "amount") else "raw", raw)
                if vk == "deductible":
                    value = f"Deductible {raw.strip()}{(' ' + m.group(2)) if m.lastindex and m.lastindex >= 2 and m.group(2) else ''}"
                out.append({"field": field, "value": value, "confidence": conf, "source_phrase": m.group(0).strip(),
                            "kind": kind, "method": "rule"})
        for rx, field, label in FLAGS:
            if (m := rx.search(text)):
                out.append({"field": field, "value": label, "confidence": 90, "source_phrase": m.group(0), "kind": "flag", "method": "rule"})
        return out

    def _ai(self, items: list[dict], results: dict) -> None:
        batch = get_settings().max_rows_to_llm
        for start in range(0, len(items), batch):
            chunk = items[start:start + batch]
            try:
                out = self.llm.json("free-text extraction", P.SYSTEM, P.build(chunk), 2500)
            except LLMUnavailable as e:
                self.log("AI extraction skipped", f"{e}. Rule-based extraction only.", "warn")
                return
            for r in out if isinstance(out, list) else []:
                row = results.get(int(r.get("row", -1))) if str(r.get("row", "")).lstrip("-").isdigit() else None
                if not row:
                    continue
                have = {(x["field"], str(x["value"]).lower()) for x in row["extracted"]}
                for x in r.get("extracted", []):
                    if not x.get("field") or (x["field"], str(x.get("value", "")).lower()) in have:
                        continue
                    # the model must quote text that really exists in the note
                    if x.get("source_phrase") and x["source_phrase"].lower() not in row["text"].lower():
                        continue
                    row["extracted"].append({**x, "kind": x.get("kind", "fact"), "method": "ai",
                                             "confidence": int(x.get("confidence") or 0)})

    def _merge(self, enriched: list[dict], results: dict, threshold: int) -> int:
        merged = 0
        for row_no, res in results.items():
            row = enriched[row_no - 1]
            for x in res["extracted"]:
                if x["kind"] == "fact" and x["confidence"] >= threshold and not row.get(x["field"]):
                    row[x["field"]] = str(x["value"])
                    row.setdefault("_ft_filled", []).append(x["field"])
                    merged += 1
                else:
                    row.setdefault("_ft_annotations", []).append(f"{x['field']}={x['value']} ({x['kind']}, {x['confidence']}%)")
        return merged
