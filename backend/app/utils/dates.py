"""Date parsing with explicit ambiguity handling.

Bordereaux mix DD/MM/YYYY (UK) and MM/DD/YYYY (US) in the same file, and
sometimes send year-only values. We never silently guess: every parse returns
how it was interpreted so the Validation Agent can flag ambiguity."""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

_SEP = re.compile(r"[./-]")


@dataclass
class ParsedDate:
    value: date | None
    fmt: str            # 'iso','dmy','mdy','year_only','excel_serial','text','invalid','blank'
    ambiguous: bool = False
    note: str = ""

    @property
    def iso(self) -> str:
        return self.value.isoformat() if self.value else ""


def _mk(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _year(y: int) -> int:
    return y + 2000 if y < 100 else y


def parse_date(raw, prefer: str = "dmy") -> ParsedDate:
    """prefer='dmy' for London-market bordereaux; 'mdy' if coverholder is US."""
    if raw is None:
        return ParsedDate(None, "blank")
    if isinstance(raw, datetime):
        return ParsedDate(raw.date(), "iso")
    if isinstance(raw, date):
        return ParsedDate(raw, "iso")
    s = str(raw).strip()
    if not s or s.lower() in {"nan", "none", "null", "n/a", "-", "nat"}:
        return ParsedDate(None, "blank")

    if re.fullmatch(r"\d{5}(\.0+)?", s):  # Excel serial (e.g. 46113)
        return ParsedDate(date(1899, 12, 30) + timedelta(days=int(float(s))), "excel_serial")

    if re.fullmatch(r"(19|20)\d{2}", s):  # year only -> cannot load as a date
        return ParsedDate(None, "year_only", note=f"year-only value '{s}'")

    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)  # ISO
    if m:
        d = _mk(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        return ParsedDate(d, "iso" if d else "invalid")

    parts = _SEP.split(s.split(" ")[0])
    if len(parts) == 3 and all(p.isdigit() for p in parts):
        a, b, c = (int(p) for p in parts)
        y = _year(c)
        if a > 12 and b <= 12:
            d = _mk(y, b, a)
            return ParsedDate(d, "dmy" if d else "invalid")
        if b > 12 and a <= 12:
            d = _mk(y, a, b)
            return ParsedDate(d, "mdy" if d else "invalid", note="US month/day order detected")
        if a <= 12 and b <= 12:
            if a == b:
                return ParsedDate(_mk(y, a, b), prefer)
            d = _mk(y, b, a) if prefer == "dmy" else _mk(y, a, b)
            return ParsedDate(d, prefer, ambiguous=True, note=f"ambiguous day/month, assumed {prefer.upper()}")
        return ParsedDate(None, "invalid", note=f"unparseable '{s}'")

    for fmt in ("%d %b %y", "%d %b %Y", "%d %B %Y", "%d %B %y", "%b %d %Y", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return ParsedDate(datetime.strptime(s, fmt).date(), "text")
        except ValueError:
            continue
    return ParsedDate(None, "invalid", note=f"unparseable '{s}'")


def column_date_preference(values: list) -> str:
    """Majority vote over a column's unambiguous values: 'dmy' or 'mdy'."""
    dmy = mdy = 0
    for v in values:
        p = parse_date(v)
        if p.fmt == "dmy" and not p.ambiguous:
            dmy += 1
        elif p.fmt == "mdy" and not p.ambiguous:
            mdy += 1
    return "mdy" if mdy > dmy else "dmy"
