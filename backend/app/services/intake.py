"""Intake = the moment a file arrives (upload, email attachment, SFTP).
Stores the original immutably, fingerprints it, identifies the coverholder,
creates the BDX Inbox row and enqueues the pipeline."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.db.models import BdxFile, Coverholder
from app.memory import operational
from app.parsers.factory import needs_password
from app.storage.base import ImmutableBlobError
from app.storage.factory import get_store
from app.utils.hashing import sha256_bytes


def identify_coverholder(db: Session, filename: str, sender: str = "") -> Coverholder | None:
    fn = filename.lower()
    sender = (sender or "").lower()
    for ch in db.query(Coverholder).all():
        names = [ch.name.lower()] + [a.lower() for a in (ch.aliases or [])]
        if any(n and (fn.startswith(n.replace(" ", "")) or fn.startswith(n.replace(" ", "_")) or n in fn) for n in names):
            return ch
        if sender and any(sender.endswith(e.lower()) for e in (ch.sender_emails or [])):
            return ch
    return None


def next_sla(received: datetime, day: int) -> datetime:
    """Bordereaux are due by the Nth of the month following the reporting month."""
    y, m = received.year, received.month
    due = datetime(y, m, min(day, 28), tzinfo=timezone.utc)
    if received >= due:
        m = 1 if m == 12 else m + 1
        y = y + 1 if m == 1 else y
        due = datetime(y, m, min(day, 28), tzinfo=timezone.utc)
    return due


def receive_file(db: Session, *, filename: str, data: bytes, source: str, source_ref: str = "",
                 sender: str = "", coverholder_hint: str = "", sla_day: int = 15) -> BdxFile:
    digest = sha256_bytes(data)
    dup = db.query(BdxFile).filter(BdxFile.sha256 == digest, BdxFile.status != "duplicate").first()

    ch = None
    if coverholder_hint:
        ch = db.query(Coverholder).filter(Coverholder.name.ilike(coverholder_hint)).first()
    ch = ch or identify_coverholder(db, filename, sender)
    ch_name = ch.name if ch else (coverholder_hint or filename.split("_")[0] or "Unknown")

    now = datetime.now(timezone.utc)
    f = BdxFile(filename=filename, source=source, source_ref=source_ref, sha256=digest, size_bytes=len(data),
                coverholder_id=ch.id if ch else None, coverholder_name=ch_name, received_at=now,
                sla_due=next_sla(now, sla_day))
    db.add(f)
    db.flush()

    if dup:
        f.status = "duplicate"
        f.error = f"Identical file already received ({dup.filename}, {dup.received_at:%d %b %Y}). Not reprocessed."
        operational.record(db, "Ingestion Agent", "Duplicate file rejected", f.error, file_id=f.id, level="warn")
        db.commit()
        return f

    key = f"{now:%Y/%m}/{f.id}/{filename}"
    try:
        f.raw_uri = get_store().put_raw(key, data)
    except ImmutableBlobError:
        f.raw_uri = key
    f.password_protected = needs_password(filename, data)
    f.status = "received"
    operational.record(db, "Ingestion Agent", "File received",
                       f"{filename} via {source} ({len(data):,} bytes, sha256 {digest[:12]}…)", file_id=f.id)
    db.commit()
    return f


def raw_key(f: BdxFile) -> str:
    return f"{f.received_at:%Y/%m}/{f.id}/{f.filename}"
