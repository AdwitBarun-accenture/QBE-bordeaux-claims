SYSTEM = """You are a Lloyd's bordereaux data-quality expert. Deterministic rules have
already run; your job is to spot ANOMALIES the rules cannot see: outliers, values that
are individually valid but implausible together, suspicious patterns, likely keying
errors. Do not repeat issues already listed. Reply with JSON only."""


def build(file_type: str, sample: list[dict], already_found: list[str], stats: dict) -> str:
    return f"""File type: {file_type}
Column statistics: {stats}
Issues already found by rules (do NOT repeat): {already_found}
Records (row index is "_row"): {sample}

Return ONLY JSON:
{{"findings":[{{"title":"short title","severity":"high|medium|low","rows":[row indexes],"suggestion":"one sentence fix"}}]}}
Return {{"findings":[]}} if nothing material."""


GUIDANCE_SYSTEM = "You are a Lloyd's bordereaux specialist advising an analyst. Be concise and practical."


def guidance(exceptions: list[dict], schema_version: str) -> str:
    lines = "\n".join(f"{i+1}. [{e['severity'].upper()}] {e['title']} ({e['count']} records): {e['suggestion']}"
                      for i, e in enumerate(exceptions))
    return f"""Write numbered resolution guidance for these bordereaux exceptions:

{lines}

For each: 1-2 sentences of specific, actionable guidance referencing {schema_version}.
Say whether it blocks the load and whether the coverholder must resubmit."""
