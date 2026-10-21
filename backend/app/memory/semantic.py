"""Semantic memory: approved column->LCRS pairs per coverholder + file type.
Recalled at 100% confidence on the next run (no LLM call needed)."""
from sqlalchemy.orm import Session

from app.db.models import SemanticMapping


def recall(db: Session, coverholder: str, file_type: str) -> dict[str, SemanticMapping]:
    rows = db.query(SemanticMapping).filter_by(coverholder_name=coverholder, file_type=file_type).all()
    return {r.source_column.strip().lower(): r for r in rows}


def remember(db: Session, coverholder: str, file_type: str, mappings: list[dict], approved_by: str,
             auto_threshold: int) -> int:
    """Store pairs that a human approved at Gate 1: auto-mapped >= threshold,
    human-corrected, or formula. Corrections overwrite earlier memory."""
    existing = recall(db, coverholder, file_type)
    added = 0
    for m in mappings:
        if m.get("canonical") in (None, "", "unmapped") and not m.get("formula"):
            continue
        origin = "formula" if m.get("formula") else ("human" if m.get("human_corrected") else "auto")
        if origin == "auto" and (m.get("confidence") or 0) < auto_threshold:
            continue
        key = m["source"].strip().lower()
        row = existing.get(key)
        if row:
            if row.canonical != m["canonical"] or origin != "auto":
                row.canonical, row.origin, row.formula = m["canonical"], origin, m.get("formula")
                row.approved_by = approved_by
            continue
        db.add(SemanticMapping(coverholder_name=coverholder, file_type=file_type, source_column=m["source"],
                               canonical=m["canonical"], origin=origin, confidence=100, formula=m.get("formula"),
                               approved_by=approved_by))
        added += 1
    db.flush()
    return added


def list_all(db: Session) -> list[dict]:
    return [{"coverholder": r.coverholder_name, "file_type": r.file_type, "source": r.source_column,
             "canonical": r.canonical, "origin": r.origin, "approved_by": r.approved_by, "times_used": r.times_used}
            for r in db.query(SemanticMapping).order_by(SemanticMapping.coverholder_name).all()]


def forget(db: Session, coverholder: str, file_type: str, source_column: str) -> None:
    db.query(SemanticMapping).filter_by(coverholder_name=coverholder, file_type=file_type,
                                        source_column=source_column).delete()
    db.commit()
