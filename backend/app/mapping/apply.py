"""Apply approved mappings to source rows -> canonical rows (values still raw
strings; typing happens in validation/cleansing). '_row' keeps the 1-based
source row number for lineage."""
from app.mapping.formula import evaluate


def active(m: dict, review_threshold: int) -> bool:
    if m.get("formula"):
        return True
    return m.get("canonical") not in (None, "", "unmapped") and (m.get("confidence") or 0) >= review_threshold


def apply_mappings(rows: list[dict], mappings: list[dict], review_threshold: int = 50) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        c = {"_row": i + 1}
        for m in mappings:
            if not active(m, review_threshold):
                continue
            if m.get("formula"):
                val = evaluate(m["formula"], r)
                if val != "":
                    c[m["formula"]["target"]] = val
            else:
                c[m["canonical"]] = r.get(m["source"], "")
        out.append(c)
    return out
