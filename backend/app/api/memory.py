from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db.models import User
from app.db.session import get_db
from app.memory import episodic, operational, semantic
from app.security.auth import analyst_only

router = APIRouter(prefix="/api/memory", tags=["memory"])


@router.get("")
def get_memory(db: Session = Depends(get_db), _: User = Depends(analyst_only)):
    return {"episodic": episodic.list_all(db), "semantic": semantic.list_all(db), "operational": operational.recent(db),
            "token_usage": operational.token_usage(db)}


class ForgetIn(BaseModel):
    coverholder: str
    file_type: str
    source: str


@router.post("/semantic/forget")
def forget(body: ForgetIn, db: Session = Depends(get_db), _: User = Depends(analyst_only)):
    semantic.forget(db, body.coverholder, body.file_type, body.source)
    return {"ok": True}
