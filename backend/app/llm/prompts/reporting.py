SUMMARY_SYSTEM = "You are a senior Lloyd's bordereaux analyst writing for underwriting management. Formal consulting style, no bullet points."


def summary(ctx: dict) -> str:
    return f"""Write a concise executive summary (3 short paragraphs) of this bordereaux processing run.

File: {ctx['filename']} | Coverholder: {ctx['coverholder']} | Type: {ctx['file_type']}
Records: {ctx['records']} | Overall quality: {ctx['quality']}% (completeness {ctx['scores'].get('completeness')}%, accuracy {ctx['scores'].get('accuracy')}%, consistency {ctx['scores'].get('consistency')}%)
Columns mapped: {ctx['mapped']}/{ctx['columns']} | Control total gross (GBP): {ctx.get('gbp_total')}
Open exceptions: {ctx['exceptions']}
Reconciliation: {ctx['recon']}

Paragraph 1: what was processed and the overall quality verdict.
Paragraph 2: key exceptions and their materiality.
Paragraph 3: recommended next steps (load, partial load, or request resubmission)."""


DUA_SYSTEM = "You draft professional, courteous emails from a Lloyd's managing agent's bordereaux team to a coverholder (DUA/TPA)."


def dua_email(ctx: dict) -> str:
    return f"""Draft an email to {ctx['coverholder']} about their bordereaux file '{ctx['filename']}'.
Outcome: {ctx['outcome']}. Analyst comment: {ctx.get('comment') or 'none'}.
Issues to resolve:
{ctx['issues']}
Ask for a corrected resubmission by {ctx['deadline']}. Include a subject line as the first line 'Subject: ...'."""
