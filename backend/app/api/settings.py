from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.lcrs_schema import FIELDS
from app.core.runtime_settings import get_pipeline_settings, update_pipeline_settings
from app.db.models import Coverholder, User
from app.db.session import get_db
from app.mapping.formula import OPS
from app.security.auth import analyst_only, any_user
from app.security.vault import get_vault

router = APIRouter(prefix="/api", tags=["settings"])


@router.get("/settings")
def read_settings(db: Session = Depends(get_db), _: User = Depends(analyst_only)):
    return get_pipeline_settings(db)


@router.put("/settings")
def write_settings(patch: dict, db: Session = Depends(get_db), _: User = Depends(analyst_only)):
    if "auto_approve_threshold" in patch and not 50 <= int(patch["auto_approve_threshold"]) <= 100:
        raise HTTPException(400, "auto_approve_threshold must be 50-100")
    return update_pipeline_settings(db, patch)


class CoverholderIn(BaseModel):
    name: str
    class_of_business: str = ""
    da_limit_gbp: float = 0
    date_order: str = "dmy"
    aliases: list[str] = []
    sender_emails: list[str] = []


def _ch(c: Coverholder, saved: set) -> dict:
    return {"id": c.id, "name": c.name, "class_of_business": c.class_of_business, "da_limit_gbp": c.da_limit_gbp,
            "date_order": c.date_order, "aliases": c.aliases, "sender_emails": c.sender_emails, "password_saved": c.name in saved}


@router.get("/coverholders")
def list_coverholders(db: Session = Depends(get_db), _: User = Depends(any_user)):
    saved = set(get_vault().list())
    return [_ch(c, saved) for c in db.query(Coverholder).order_by(Coverholder.name)]


@router.post("/coverholders")
def upsert_coverholder(body: CoverholderIn, db: Session = Depends(get_db), _: User = Depends(analyst_only)):
    c = db.query(Coverholder).filter_by(name=body.name).first() or Coverholder(name=body.name)
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.add(c)
    db.commit()
    return _ch(c, set(get_vault().list()))


@router.get("/vault")
def vault_list(_: User = Depends(analyst_only)):
    return [n for n in get_vault().list() if not n.startswith("__job__")]


@router.delete("/vault/{coverholder}")
def vault_delete(coverholder: str, _: User = Depends(analyst_only)):
    get_vault().delete(coverholder)
    return {"ok": True}


@router.get("/meta/lcrs-fields")
def lcrs_fields(_: User = Depends(any_user)):
    return [{"name": f.name, "type": f.dtype.value, "description": f.description, "mandatory_for": [m.value for m in f.mandatory_for],
             "derived": f.derived} for f in FIELDS]


@router.get("/meta/formula-ops")
def formula_ops(_: User = Depends(any_user)):
    return OPS
