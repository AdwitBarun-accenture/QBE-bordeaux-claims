"""Episodic memory: one record per finished run, used to (a) show prior history
when a new file arrives and (b) detect structural changes in a coverholder's layout."""
from sqlalchemy.orm import Session

from app.db.models import EpisodicMemory
from app.utils.hashing import headers_signature


def last_for(db: Session, coverholder: str, file_type: str) -> EpisodicMemory | None:
    return (db.query(EpisodicMemory).filter_by(coverholder_name=coverholder, file_type=file_type)
            .order_by(EpisodicMemory.at.desc()).first())


def history(db: Session, coverholder: str, limit: int = 5) -> list[dict]:
    rows = (db.query(EpisodicMemory).filter_by(coverholder_name=coverholder)
            .order_by(EpisodicMemory.at.desc()).limit(limit).all())
    return [_to_dict(r) for r in rows]


def save(db: Session, *, coverholder, file_type, file_id, run_id, filename, headers, quality, exceptions, hitl, outcome):
    db.add(EpisodicMemory(coverholder_name=coverholder, file_type=file_type, file_id=file_id, run_id=run_id,
                          filename=filename, headers=headers, headers_signature=headers_signature(headers),
                          quality=quality, exception_count=len(exceptions),
                          exception_titles=[e for e in exceptions][:20], hitl=hitl, outcome=outcome))
    db.flush()


def structural_change(db: Session, coverholder: str, file_type: str, headers: list[str]) -> dict:
    prev = last_for(db, coverholder, file_type)
    if not prev:
        return {"first_run": True, "changed": False}
    old, new = set(h.lower() for h in prev.headers), set(h.lower() for h in headers)
    added = [h for h in headers if h.lower() not in old]
    removed = [h for h in prev.headers if h.lower() not in new]
    order_changed = not added and not removed and [h.lower() for h in headers] != [h.lower() for h in prev.headers]
    return {"first_run": False, "changed": bool(added or removed or order_changed), "added": added,
            "removed": removed, "order_changed": order_changed, "previous_file": prev.filename,
            "previous_signature": prev.headers_signature, "signature": headers_signature(headers)}


def list_all(db: Session, limit: int = 100) -> list[dict]:
    return [_to_dict(r) for r in db.query(EpisodicMemory).order_by(EpisodicMemory.at.desc()).limit(limit).all()]


def _to_dict(r: EpisodicMemory) -> dict:
    return {"coverholder": r.coverholder_name, "file_type": r.file_type, "filename": r.filename,
            "at": r.at.isoformat(), "quality": r.quality, "exceptions": r.exception_count,
            "exception_titles": r.exception_titles, "hitl": r.hitl, "outcome": r.outcome}
