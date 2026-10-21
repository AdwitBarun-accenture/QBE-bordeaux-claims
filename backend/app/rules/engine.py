"""Runs every registered rule that applies to the file type, then computes the
three quality scores the UI shows (completeness / accuracy / consistency)."""
from app.core.lcrs_schema import mandatory_fields
from app.rules import claims_rules, common_rules, premium_rules  # noqa: F401  (register rules)
from app.rules.base import REGISTRY, SEVERITY_TO_EXCEPTION, RuleContext, RuleResult
from app.rules.helpers import blank


def run_rules(ctx: RuleContext) -> list[RuleResult]:
    results = []
    for cls in REGISTRY:
        rule = cls()
        if ctx.file_type not in rule.applies_to:
            continue
        missing = [f for f in rule.requires if f not in ctx.mapped_fields]
        if missing:
            results.append(rule.skipped(f"{', '.join(missing)} not mapped"))
            continue
        try:
            results.append(rule.check(ctx))
        except Exception as e:  # a buggy rule must never kill the pipeline
            r = rule.skipped(f"rule error: {e}")
            r.severity = "warning"
            results.append(r)
    return results


def compute_scores(ctx: RuleContext, results: list[RuleResult], weights: dict) -> dict:
    n = len(ctx.rows) or 1
    req = mandatory_fields(ctx.file_type)
    cells = n * len(req) or 1
    filled = sum(1 for r in ctx.rows for f in req if not blank(r, f))
    completeness = round(filled / cells * 100)

    def pct_clean(dim: str) -> int:
        """A row failing an error-level rule costs 1 row; a row failing only
        warning-level rules costs half a row; info rules don't affect the score."""
        err, warn = set(), set()
        for res in results:
            if res.dimension != dim or res.passed or res.skipped:
                continue
            if res.severity == "error":
                err.update(res.failing_rows)
            elif res.severity == "warning":
                warn.update(res.failing_rows)
        penalty = len(err) + 0.5 * len(warn - err)
        return round((n - penalty) / n * 100)

    accuracy, consistency = pct_clean("accuracy"), pct_clean("consistency")
    w = weights or {"completeness": 1, "accuracy": 1, "consistency": 1}
    tw = sum(w.values()) or 1
    overall = round((completeness * w["completeness"] + accuracy * w["accuracy"] + consistency * w["consistency"]) / tw)
    return {"completeness": completeness, "accuracy": accuracy, "consistency": consistency, "overall": overall}


def to_exceptions(results: list[RuleResult]) -> list[dict]:
    out = []
    for r in results:
        if r.passed or r.skipped:
            continue
        out.append({"rule_id": r.rule_id, "title": r.exception_title or r.rule, "severity": SEVERITY_TO_EXCEPTION[r.severity],
                    "count": r.count, "rows": r.failing_rows, "suggestion": f"{r.detail}. {r.suggestion}".strip(". ") + ".",
                    "source": "rule"})
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda e: (order[e["severity"]], -e["count"]))
