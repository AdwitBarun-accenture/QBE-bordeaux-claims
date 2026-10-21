"""Robust numeric parsing for bordereaux values: '1,250,000', '2.5m', '45k',
'(1,200)' (accounting negative), '12.5%', '£45,200'."""
import re
from decimal import Decimal, InvalidOperation

_CURRENCY_SYMBOLS = "£$€¥"
_SUFFIX = {"k": Decimal(1_000), "m": Decimal(1_000_000), "bn": Decimal(1_000_000_000), "b": Decimal(1_000_000_000)}
_NUM_RE = re.compile(r"^([+-]?\d+(?:\.\d+)?)(k|m|bn|b)?$", re.I)


def parse_decimal(value) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float, Decimal)):
        try:
            d = Decimal(str(value))
            return None if d.is_nan() else d
        except InvalidOperation:
            return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null", "n/a", "-"}:
        return None
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace(",", "").replace(" ", "").rstrip("%")
    for sym in _CURRENCY_SYMBOLS:
        s = s.replace(sym, "")
    s = re.sub(r"^(GBP|USD|EUR)", "", s, flags=re.I)
    m = _NUM_RE.match(s)
    if not m:
        return None
    num = Decimal(m.group(1))
    if m.group(2):
        num *= _SUFFIX[m.group(2).lower()]
    return -num if negative else num


def parse_float(value) -> float | None:
    d = parse_decimal(value)
    return float(d) if d is not None else None


def approx_equal(a: float, b: float, rel_tol: float = 0.01, abs_tol: float = 1.0) -> bool:
    """Bordereaux arithmetic is rounded; allow 1% or 1 unit of tolerance."""
    return abs(a - b) <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def fmt_num(value, dp: int = 2) -> str:
    """Render a number without trailing zeros: 6780.00 -> '6780', 0.79 -> '0.79'."""
    if value is None:
        return ""
    q = Decimal(str(value)).quantize(Decimal(1) / (Decimal(10) ** dp))
    s = format(q, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s
