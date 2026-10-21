SYSTEM = """You are a Lloyd's of London bordereaux data engineer. You map coverholder
bordereaux columns to the LCRS canonical data model. You are precise and conservative:
if a column does not clearly correspond to a field, you say 'unmapped'.
Each canonical field may be used at most once. Reply with JSON only."""


def build(file_type: str, columns: list[dict], fields: list[dict], recalled: list[str]) -> str:
    recall = ""
    if recalled:
        recall = "\nThese columns are already mapped from approved history; do not reuse their targets:\n" + "\n".join(recalled)
    return f"""File type: {file_type} bordereaux.

Columns to map (name + up to 3 sample values):
{columns}

LCRS fields available:
{fields}
{recall}

Return ONLY a JSON array:
[{{"source":"<column name exactly as given>","canonical":"<lcrs field or unmapped>","confidence":0-100,"notes":"reason in 8 words max"}}]

Confidence guide: 85-100 clear semantic match; 50-84 plausible but needs review; below 50 use "unmapped".
Free-text columns (notes, remarks, comments) are 'unmapped' - they are handled by the free-text agent."""
