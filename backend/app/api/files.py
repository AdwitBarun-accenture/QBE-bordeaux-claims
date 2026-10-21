"""BDX Inbox: list, upload, unlock, reprocess."""
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.serializers import file_out
from app.core.runtime_settings import get_pipeline_settings
from app.db.models import BdxFile, User
from app.db.session import get_db
from app.security.auth import analyst_only, any_user
from app.services.intake import receive_file
from app.workers.queue import get_queue

router = APIRouter(prefix="/api/files", tags=["inbox"])
MAX_UPLOAD = 50 * 1024 * 1024


@router.get("")
def list_files(q: str = "", filter: str = Query("all", pattern="^(all|review|processed|email|sftp|upload|failed)$"),
               db: Session = Depends(get_db), _: User = Depends(any_user)):
    query = db.query(BdxFile)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(BdxFile.coverholder_name.ilike(like), BdxFile.filename.ilike(like)))
    if filter == "review":
        query = query.filter(or_(BdxFile.hitl_gate.is_not(None), BdxFile.status == "awaiting-password"))
    elif filter == "processed":
        query = query.filter(BdxFile.status == "processed")
    elif filter == "failed":
        query = query.filter(BdxFile.status.in_(["failed", "rejected", "duplicate"]))
    elif filter in ("email", "sftp", "upload"):
        query = query.filter(BdxFile.source == filter)
    files = query.order_by(BdxFile.received_at.desc()).limit(500).all()
    total = db.query(BdxFile).count()
    pending = db.query(BdxFile).filter(BdxFile.hitl_gate.is_not(None)).count()
    return {"files": [file_out(f) for f in files], "total": total, "pending_review": pending}


@router.post("/upload")
async def upload(file: UploadFile = File(...), coverholder: str = Form(""), password: str = Form(""),
                 remember: bool = Form(False), db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    data = await file.read()
    if len(data) > MAX_UPLOAD:
        raise HTTPException(413, "File larger than 50 MB")
    if not data:
        raise HTTPException(400, "Empty file")
    f = receive_file(db, filename=file.filename, data=data, source="upload", coverholder_hint=coverholder,
                     sla_day=get_pipeline_settings(db)["sla_day_of_month"])
    if f.status == "received":
        f.status = "running"
        db.commit()
        get_queue().enqueue({"type": "start", "file_id": f.id, "password": password or None, "remember": remember,
                             "user": user.email})
    return file_out(f)


@router.get("/{file_id}")
def get_file(file_id: str, db: Session = Depends(get_db), _: User = Depends(any_user)):
    f = db.get(BdxFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    return file_out(f)


class UnlockIn(BaseModel):
    password: str
    remember: bool = False
    sheet: str | None = None


@router.post("/{file_id}/unlock")
def unlock(file_id: str, body: UnlockIn, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    f = db.get(BdxFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    if f.status not in ("awaiting-password", "failed"):
        raise HTTPException(409, f"File is {f.status}")
    f.status = "running"
    db.commit()
    get_queue().enqueue({"type": "start", "file_id": f.id, "password": body.password, "remember": body.remember,
                         "sheet": body.sheet, "user": user.email})
    return file_out(f)


class ReprocessIn(BaseModel):
    sheet: str | None = None


@router.post("/{file_id}/reprocess")
def reprocess(file_id: str, body: ReprocessIn, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    """Start a fresh run (e.g. after a different sheet is chosen or settings changed)."""
    f = db.get(BdxFile, file_id)
    if not f:
        raise HTTPException(404, "File not found")
    if f.status in ("running", "duplicate"):
        raise HTTPException(409, f"File is {f.status}")
    f.status = "running"
    db.commit()
    get_queue().enqueue({"type": "start", "file_id": f.id, "sheet": body.sheet, "user": user.email})
    return file_out(f)
