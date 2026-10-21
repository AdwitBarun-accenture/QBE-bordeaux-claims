from app.utils.dates import parse_date
from app.utils.numbers import parse_float
from app.utils.reference import load_ref
from app.utils.text import clean_str, is_blank


def val(row: dict, field: str) -> str:
    return clean_str(row.get(field, ""))


def num(row: dict, field: str) -> float | None:
    return parse_float(row.get(field))


def dt(row: dict, field: str, order: str):
    return parse_date(row.get(field), order)


def blank(row: dict, field: str) -> bool:
    return is_blank(row.get(field))


def cob_lookup(raw: str) -> str | None:
    """Return canonical COB code for a raw value, or None if unrecognised."""
    v = clean_str(raw).lower()
    codes = load_ref("cob_codes")["codes"]
    for code, meta in codes.items():
        if v == code.lower() or v in meta["aliases"]:
            return code
    return None


def currency_lookup(raw: str) -> str | None:
    ref = load_ref("currencies")
    v = clean_str(raw)
    if v.upper() in ref["iso"]:
        return v.upper()
    return ref["aliases"].get(v.lower())
