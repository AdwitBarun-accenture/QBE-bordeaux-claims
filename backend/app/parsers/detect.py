"""Classify a parsed file as premium or claims bordereaux."""
from app.utils.text import normalise_header

CLAIM_WORDS = ("claim", "loss date", "date of loss", "reserve", "incurred", "notified", "paid", "o s", "outstanding")
PREMIUM_WORDS = ("prem", "umr", "inception", "on risk", "expiry", "off risk", "sum ins", "eml", "line", "comm")


def detect_file_type(filename: str, headers: list[str]) -> tuple[str, float]:
    fn = filename.lower()
    hs = " | ".join(normalise_header(h) for h in headers)
    c = sum(hs.count(w) for w in CLAIM_WORDS) + (3 if "claim" in fn else 0)
    p = sum(hs.count(w) for w in PREMIUM_WORDS) + (3 if "prem" in fn or "risk" in fn else 0)
    total = c + p or 1
    return ("claims", c / total) if c > p else ("premium", p / total)
