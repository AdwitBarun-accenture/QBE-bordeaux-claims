"""Deterministic column matcher (no AI): synonyms, fuzzy matching and value
patterns. Runs before the LLM so that obvious columns cost nothing and the LLM
only sees the genuinely ambiguous ones."""
import re

from rapidfuzz import fuzz

from app.core.lcrs_schema import FIELDS, FileType
from app.utils.text import is_blank, normalise_header

GROUPS = {
    "premium": {"policy", "insured", "risk", "premium", "broker", "coverholder"},
    "claims": {"policy", "insured", "risk", "claim", "broker", "coverholder"},
}
FREE_TEXT_HEADER = re.compile(r"note|remark|comment|narrative|description|cause of loss|circumstance", re.I)
UMR_RE = re.compile(r"^B\d{4}[A-Z0-9]{4,}$", re.I)
CLAIM_REF_RE = re.compile(r"^CLM[-/ ]?\d{2,4}[-/ ]?\d+", re.I)


def candidate_fields(file_type: str):
    g = GROUPS[FileType(file_type).value]
    return [f for f in FIELDS if not f.derived and f.group in g]


def is_free_text_column(header: str, values: list[str]) -> bool:
    vals = [v for v in values if not is_blank(v)]
    avg = sum(len(v) for v in vals) / len(vals) if vals else 0
    return bool(FREE_TEXT_HEADER.search(header)) and (avg > 25 or not vals) or avg > 60


def value_hint(values: list[str]) -> str | None:
    vals = [v.strip() for v in values if not is_blank(v)][:20]
    if not vals:
        return None
    if sum(bool(UMR_RE.match(v)) for v in vals) / len(vals) > 0.6:
        return "policy.unique_market_reference"
    if sum(bool(CLAIM_REF_RE.match(v)) for v in vals) / len(vals) > 0.6:
        return "claim.reference"
    return None


def match_column(header: str, values: list[str], file_type: str) -> dict:
    """Return best deterministic guess: {canonical, confidence, notes, origin}."""
    h = normalise_header(header)
    cands = candidate_fields(file_type)
    synonyms = {f.name: [normalise_header(s) for s in f.synonyms] + [normalise_header(f.name.split(".")[1].replace("_", " "))]
                for f in cands}
    for f in cands:                       # 1a) exact explicit synonym wins (incl. 'Cause of Loss')
        if h in [normalise_header(x) for x in f.synonyms]:
            return {"canonical": f.name, "confidence": 95, "notes": "exact synonym match", "origin": "rule"}
    for f in cands:                       # 1b) then the field's own leaf name ('status' -> only if no explicit hit)
        if h == normalise_header(f.name.split(".")[1].replace("_", " ")):
            return {"canonical": f.name, "confidence": 90, "notes": "matches field name", "origin": "rule"}
    if is_free_text_column(header, values):   # 2) notes/remarks with no canonical home
        return {"canonical": "unmapped", "confidence": 0, "notes": "free text -> Classification Agent", "origin": "rule",
                "free_text": True}
    best = ("unmapped", 0, "")
    for f in cands:                       # 3) fuzzy
        names = synonyms[f.name]
        score = max(fuzz.token_sort_ratio(h, n) for n in names)
        if score > best[1]:
            best = (f.name, score, f"fuzzy {score}% on header")
    hint = value_hint(values)
    if hint and hint in {f.name for f in candidate_fields(file_type)}:
        return {"canonical": hint, "confidence": 90, "notes": "value pattern match", "origin": "rule"}
    name, score, note = best
    if score >= 92:
        conf = 86
    elif score >= 80:
        conf = 65
    elif score >= 70:
        conf = 50
    else:
        return {"canonical": "unmapped", "confidence": 0, "notes": "no confident rule match", "origin": "rule"}
    return {"canonical": name, "confidence": conf, "notes": note, "origin": "rule"}


def resolve_conflicts(mappings: list[dict]) -> list[dict]:
    """A canonical field can only be fed by one source column: keep the most
    confident; demote the others to review with a note."""
    by_target: dict[str, list[dict]] = {}
    for m in mappings:
        if m["canonical"] != "unmapped" and not m.get("formula"):
            by_target.setdefault(m["canonical"], []).append(m)
    for target, ms in by_target.items():
        if len(ms) < 2:
            continue
        ms.sort(key=lambda x: (x.get("origin") in ("memory", "human"), x["confidence"]), reverse=True)
        for loser in ms[1:]:
            loser["notes"] = f"conflicts with '{ms[0]['source']}' for {target}"
            loser["canonical"], loser["confidence"] = "unmapped", 0
    return mappings
