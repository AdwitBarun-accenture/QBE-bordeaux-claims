"""Text helpers used by parsers, mapping and cleansing."""
import re
import unicodedata

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9%]+")
EMAIL_RE = re.compile(r"^[\w.+-]+@[\w-]+\.[\w.-]+$")


def clean_str(value) -> str:
    """Trim, collapse whitespace, strip non-printables. None -> ''."""
    if value is None:
        return ""
    s = str(value)
    s = unicodedata.normalize("NFKC", s)
    s = "".join(ch for ch in s if ch.isprintable() or ch in "\n\t")
    return _WS.sub(" ", s).strip()


def normalise_header(h: str) -> str:
    """'Net Prem Written ' -> 'net prem written' (used for synonym matching)."""
    return _WS.sub(" ", _NON_ALNUM.sub(" ", clean_str(h).lower())).strip()


def is_blank(value) -> bool:
    if value is None:
        return True
    s = str(value).strip()
    return s == "" or s.lower() in {"nan", "none", "null", "n/a", "na", "-", "--"}


def dedupe_headers(headers: list[str]) -> list[str]:
    """Excel exports often repeat headers ('Amount', 'Amount'). Make them unique."""
    seen: dict[str, int] = {}
    out = []
    for h in headers:
        h = clean_str(h) or "Unnamed"
        if h in seen:
            seen[h] += 1
            out.append(f"{h}_{seen[h]}")
        else:
            seen[h] = 0
            out.append(h)
    return out


def looks_like_email(value: str) -> bool:
    return bool(EMAIL_RE.match(clean_str(value)))


def truncate(s: str, n: int) -> str:
    s = s or ""
    return s if len(s) <= n else s[: n - 1] + "…"
