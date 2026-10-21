"""STAGE 03 - Validation Agent (Rules + AI)

Mockup: a single LLM prompt was asked to 'apply LCRS business rules' and invent
checks, scores and exceptions. That is not auditable, so here:

  1. DETERMINISTIC RULE ENGINE (rules/*.py) - every insurance rule from the
     mockup is real code with row-level results:
       premium: mandatory fields, inception<expiry, duplicate UMR, prior-submission
                dedup, net = gross x line, EML on PROP/ENGY, sum insured present,
                COB taxonomy, mixed record types, brokerage cap, % ranges,
                numeric premium, broker code present, broker name consistency,
                DA-limit proximity
       claims : loss<=notification, loss not future, paid+O/S=incurred, duplicate
                claim ref, date of loss present, status taxonomy, handler format,
                negative reserves
       common : currency ISO 4217, date-format consistency, country codes
  2. QUALITY SCORES - completeness (mandatory cells filled), accuracy and
     consistency (% rows clean on those dimensions), weighted overall.
  3. AI ANOMALY DETECTION (optional) - the model only looks for what rules
     cannot see; findings are tagged source='ai' so reviewers know.
  4. EXCEPTIONS - severity-tiered (high/medium/low), with affected rows.
  5. AI RESOLUTION GUIDANCE - numbered advice per exception (template fallback).

Gate 2 (Exception review) opens when any open exception exists (or always, if
configured).
"""
from datetime import datetime, timezone

from app.agents.base import BaseAgent
from app.core.config import get_settings
from app.db.models import Coverholder, DataException
from app.llm.base import LLMUnavailable
from app.llm.prompts import validation as P
from app.loaders.factory import get_warehouse
from app.mapping.apply import apply_mappings
from app.rules.base import RuleContext
from app.rules.engine import compute_scores, run_rules, to_exceptions
from app.storage.factory import save_dataset
from app.utils.dates import column_date_preference
from app.utils.text import is_blank


class ValidationAgent(BaseAgent):
    name = "Validation Agent"

    def run(self) -> None:
        f, run, s, db = self.ctx.file, self.ctx.run, self.ctx.settings, self.ctx.db
        canonical = apply_mappings(self.ctx.cache["parsed"], run.mappings, s["review_threshold"])
        self.ctx.cache["canonical"] = canonical
        save_dataset(run.id, "canonical", canonical)
        mapped = {k for r in canonical for k in r if not k.startswith("_")}

        ch = db.get(Coverholder, f.coverholder_id) if f.coverholder_id else None
        date_order = ch.date_order if ch else column_date_preference(
            [r.get("policy.inception_date") or r.get("claim.date_of_loss") for r in canonical])
        wh = get_warehouse()
        ctx = RuleContext(
            rows=canonical, file_type=f.file_type, settings=s, mapped_fields=mapped, date_order=date_order,
            date_order_source="profile" if ch else "inferred",
            coverholder={"name": f.coverholder_name, "da_limit_gbp": ch.da_limit_gbp if ch else 0},
            prior_umrs=wh.prior_umrs(f.coverholder_name, exclude_file_id=f.id) if f.file_type == "premium" else set(),
            prior_written_gbp=wh.written_gbp_ytd(f.coverholder_name, datetime.now(timezone.utc).year, exclude_file_id=f.id),
        )
        self.log("Applying business rules", f"{len(canonical)} records, {len(mapped)} LCRS fields, date order {date_order.upper()}")
        results = run_rules(ctx)
        scores = compute_scores(ctx, results, s["quality_weights"])
        exceptions = to_exceptions(results)

        ai_findings = []
        if s["processing"]["ai_anomaly_detection"]:
            ai_findings = self._ai_anomalies(canonical, exceptions)
            exceptions += ai_findings

        run.validation = {"checks": [r.to_dict() for r in results], "scores": scores, "date_order": date_order,
                          "ai_findings": len(ai_findings), "rules_run": sum(not r.skipped for r in results)}
        # replace exceptions for this run (re-validation after a mapping change)
        # mutate the relationship collection itself so every later stage in this
        # session sees the same objects (delete-orphan removes the old ones)
        run.exceptions.clear()
        db.flush()
        for e in exceptions:
            run.exceptions.append(DataException(rule_id=e["rule_id"], title=e["title"], severity=e["severity"],
                                                count=e["count"], row_indexes=e["rows"], suggestion=e["suggestion"],
                                                source=e["source"]))
        db.flush()
        f.quality = scores["overall"]

        failed = [r for r in results if not r.passed and not r.skipped]
        hi = sum(e["severity"] == "high" for e in exceptions)
        self.log("Validation complete", f"{len(failed)} rule failures, {len(exceptions)} exceptions ({hi} high). "
                                        f"Quality {scores['overall']}% (C {scores['completeness']} / A {scores['accuracy']} / K {scores['consistency']})")
        run.resolution_guidance = self.guidance(exceptions)

    # ------------------------------------------------------------------
    def _ai_anomalies(self, canonical: list[dict], exceptions: list[dict]) -> list[dict]:
        n = get_settings().max_rows_to_llm
        stats = {}
        for k in {k for r in canonical for k in r if not k.startswith("_")}:
            vals = [r.get(k) for r in canonical]
            stats[k] = {"blank": sum(is_blank(v) for v in vals), "distinct": len(set(vals))}
        try:
            out = self.llm.json("anomaly detection", P.SYSTEM,
                                P.build(self.ctx.file.file_type, canonical[:n], [e["title"] for e in exceptions], stats), 1200)
        except LLMUnavailable as e:
            self.log("AI anomaly detection skipped", str(e), "warn")
            return []
        findings = []
        for x in (out.get("findings", []) if isinstance(out, dict) else []):
            if x.get("severity") not in ("high", "medium", "low") or not x.get("title"):
                continue
            rows = [int(r) for r in x.get("rows", []) if str(r).isdigit()]
            findings.append({"rule_id": "AI_ANOMALY", "title": f"[AI] {x['title']}", "severity": x["severity"],
                             "count": len(rows) or 1, "rows": rows, "suggestion": x.get("suggestion", ""), "source": "ai"})
        self.log("AI anomaly detection", f"{len(findings)} additional finding(s) beyond the rule set")
        return findings

    def guidance(self, exceptions: list[dict]) -> str:
        if not exceptions:
            return ""
        try:
            return self.llm.text("resolution guidance", P.GUIDANCE_SYSTEM,
                                 P.guidance(exceptions[:15], get_settings().schema_version), 900).text
        except LLMUnavailable:
            return "\n".join(f"{i+1}. [{e['severity'].upper()}] {e['title']} - {e['suggestion']}"
                             for i, e in enumerate(exceptions))
