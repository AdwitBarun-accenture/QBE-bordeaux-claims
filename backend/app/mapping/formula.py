"""Analyst-defined formula mappings (Formula modal in the UI):
target = colA <op> colB."""
from app.utils.numbers import fmt_num, parse_decimal

OPS = {
    "multiply": "A x B",
    "divide": "A / B",
    "add": "A + B",
    "subtract": "A - B",
    "percent": "A / B x 100   (A as a % of B)",
    "pct_of": "A x B / 100    (B% of A, e.g. gross x line%)",
}


def evaluate(formula: dict, row: dict) -> str:
    a, b = parse_decimal(row.get(formula["colA"])), parse_decimal(row.get(formula["colB"]))
    if a is None or b is None:
        return ""
    op = formula["op"]
    try:
        if op == "multiply":
            r = a * b
        elif op == "divide":
            r = a / b
        elif op == "add":
            r = a + b
        elif op == "subtract":
            r = a - b
        elif op == "percent":
            r = a / b * 100
        elif op == "pct_of":
            r = a * b / 100
        else:
            return ""
    except Exception:
        return ""
    return fmt_num(r, 4)


def validate_formula(formula: dict, headers: list[str]) -> str | None:
    if formula.get("op") not in OPS:
        return f"unknown operator {formula.get('op')}"
    for k in ("colA", "colB"):
        if formula.get(k) not in headers:
            return f"{k} '{formula.get(k)}' is not a source column"
    if not formula.get("target"):
        return "target field required"
    return None
