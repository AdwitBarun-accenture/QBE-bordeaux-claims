SYSTEM = """You are a Lloyd's claims and underwriting specialist. You extract structured
facts from bordereaux free-text notes. Only extract what the text actually states;
never infer. Quote the exact phrase you used. Reply with JSON only."""

TARGETS = """policy.endorsement_date, policy.cancellation_date, risk.description (coverage changes,
extensions, exclusions), risk.sum_insured (sub-limits only if stated as such), premium.gross_original
(premium adjustments, signed +/-), coverholder.binding_authority (DA limits), claim.reserve_gross
(reserve movements), claim.reference (cross-referenced claims), claim.description (subrogation,
business interruption, general average), claim.total_incurred, policy.reference (linked policies)"""


def build(items: list[dict]) -> str:
    body = "\n\n".join(f"[row {it['row']}] Insured: {it['insured']}\nText: {it['text']}" for it in items)
    return f"""Extract structured LCRS facts from these notes.

{body}

Target fields: {TARGETS}

Return ONLY a JSON array:
[{{"row": <row number>, "extracted":[{{"field":"lcrs.field","value":"normalised value (dates ISO yyyy-mm-dd, amounts plain numbers)","confidence":0-100,"source_phrase":"exact text used","kind":"fact|adjustment|cross_reference|flag"}}]}}]"""
