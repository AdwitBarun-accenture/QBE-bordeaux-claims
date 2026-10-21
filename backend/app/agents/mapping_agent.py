"""STAGE 02 - Mapping Agent (Parse + AI column mapping)

Mockup: one LLM call mapping every column to LCRS with a confidence score;
85+ auto-approved, 50-84 review, <50 unmapped; previously approved pairs
recalled from semantic memory at 100%.

Full implementation, in order of cost:
  1. Semantic memory   - approved pairs for this coverholder+file type (100%, free)
  2. Deterministic     - synonyms / fuzzy / value patterns (mapping/matcher.py)
  3. LLM               - only for columns still below the auto threshold;
                         combined with the rule guess (agreement boosts, disagreement -> review)
  4. Conflict resolver - one source column per canonical field
  5. Status per column - auto | review | unmapped, using runtime thresholds
  6. Mandatory coverage check - which mandatory LCRS fields have no source

Gate 1 (Mapping sign-off) opens if any column needs review, a mandatory field
is missing, the layout changed, or the gate is configured as always-on.
"""
from app.agents.base import BaseAgent
from app.core.lcrs_schema import fields_for_prompt, mandatory_fields
from app.llm.base import LLMUnavailable
from app.llm.prompts import mapping as P
from app.mapping.matcher import candidate_fields, match_column, resolve_conflicts
from app.memory import semantic
from app.utils.text import is_blank, truncate


def status_for(m: dict, auto_t: int, review_t: int) -> str:
    if m.get("formula") or m.get("human_corrected"):
        return "auto"
    if m["canonical"] == "unmapped" or m["confidence"] < review_t:
        return "unmapped"
    return "auto" if m["confidence"] >= auto_t else "review"


class MappingAgent(BaseAgent):
    name = "Mapping Agent"

    def run(self) -> None:
        f, run, s = self.ctx.file, self.ctx.run, self.ctx.settings
        rows, headers = self.ctx.cache["parsed"], self.ctx.cache["headers"]
        auto_t, review_t = s["auto_approve_threshold"], s["review_threshold"]
        samples = {h: [r.get(h, "") for r in rows if not is_blank(r.get(h))][:3] for h in headers}

        recalled = semantic.recall(self.ctx.db, f.coverholder_name, f.file_type)
        self.log("Semantic memory recall", f"{len(recalled)} approved mappings on file for {f.coverholder_name}")

        mappings: list[dict] = []
        for h in headers:
            mem = recalled.get(h.strip().lower())
            if mem:
                mem.times_used += 1
                mappings.append({"source": h, "canonical": mem.canonical, "confidence": 100, "origin": "memory",
                                 "notes": f"recalled ({mem.origin}, approved by {mem.approved_by or 'system'})",
                                 "formula": mem.formula, "human_corrected": False})
                continue
            guess = match_column(h, [r.get(h, "") for r in rows], f.file_type)
            mappings.append({"source": h, **guess, "formula": None, "human_corrected": False})

        pending = [m for m in mappings if m["origin"] != "memory" and not m.get("free_text") and m["confidence"] < 95]
        if pending:
            self._ai_pass(pending, mappings, samples, auto_t)

        mappings = resolve_conflicts(mappings)
        for m in mappings:
            m["samples"] = [truncate(v, 40) for v in samples.get(m["source"], [])]
            m["status"] = status_for(m, auto_t, review_t)
            m.pop("free_text", None)

        mapped_targets = {m["canonical"] for m in mappings if m["status"] != "unmapped"} | \
                         {m["formula"]["target"] for m in mappings if m.get("formula")}
        missing = [x for x in mandatory_fields(f.file_type) if x not in mapped_targets]
        run.mappings = mappings
        run.ingestion = {**run.ingestion, "missing_mandatory": missing}

        auto = sum(m["status"] == "auto" for m in mappings)
        review = sum(m["status"] == "review" for m in mappings)
        unm = sum(m["status"] == "unmapped" for m in mappings)
        self.log("Mapping complete", f"{auto}/{len(mappings)} auto-mapped (>= {auto_t}%), {review} for review, {unm} unmapped")
        if missing:
            self.log("Mandatory fields not mapped", ", ".join(missing), "warn")

    def needs_review(self) -> bool:
        run = self.ctx.run
        return (any(m["status"] == "review" for m in run.mappings)
                or bool(run.ingestion.get("missing_mandatory"))
                or bool(run.structural_change.get("changed")))

    # ------------------------------------------------------------------
    def _ai_pass(self, pending: list[dict], mappings: list[dict], samples: dict, auto_t: int) -> None:
        f = self.ctx.file
        locked = [f"{m['source']} -> {m['canonical']}" for m in mappings
                  if m["origin"] == "memory" or m["confidence"] >= 95]
        cols = [{"name": m["source"], "samples": samples.get(m["source"], [])} for m in pending]
        try:
            result = self.llm.json("column mapping", P.SYSTEM,
                                   P.build(f.file_type, cols, fields_for_prompt(f.file_type), locked), 2000)
        except LLMUnavailable as e:
            self.log("AI mapping skipped", f"{e}. Using rule-based mapping only.", "warn")
            return
        valid = {fd.name for fd in candidate_fields(f.file_type)}
        by_src = {str(x.get("source", "")).strip().lower(): x for x in result if isinstance(x, dict)}
        for m in pending:
            ai = by_src.get(m["source"].strip().lower())
            if not ai:
                continue
            ai_can = ai.get("canonical") if ai.get("canonical") in valid else "unmapped"
            ai_conf = int(ai.get("confidence") or 0)
            if ai_can == m["canonical"] and ai_can != "unmapped":
                m.update(confidence=min(99, max(m["confidence"], ai_conf) + 5), origin="rule+ai",
                         notes=f"rule and AI agree; {ai.get('notes', '')}")
            elif ai_can != "unmapped" and ai_conf > m["confidence"]:
                capped = ai_conf if m["canonical"] == "unmapped" else min(ai_conf, auto_t - 1)
                m.update(canonical=ai_can, confidence=capped, origin="ai",
                         notes=ai.get("notes", "") + ("" if m["canonical"] == "unmapped" else " (rule disagreed)"))
        self.log("AI mapping pass", f"{len(pending)} ambiguous columns sent to the model")
