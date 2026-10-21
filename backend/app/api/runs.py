"""Pipeline run: stage outputs, HITL gates, mapping edits, exceptions, Q&A, export."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.agents import orchestrator
from app.agents.base import AgentContext
from app.agents.insights_agent import ask_file
from app.agents.reporting_agent import ReportingAgent, export_csv
from app.api.serializers import run_out
from app.core.runtime_settings import get_pipeline_settings
from app.db.models import HitlDecision, PipelineRun, User
from app.db.session import get_db
from app.memory import operational
from app.security.auth import analyst_only, any_user
from app.storage.factory import dataset_exists, load_dataset
from app.workers.queue import get_queue

router = APIRouter(prefix="/api/runs", tags=["pipeline"])


def _run(db, run_id) -> PipelineRun:
    r = db.get(PipelineRun, run_id)
    if not r:
        raise HTTPException(404, "Run not found")
    return r


@router.get("/{run_id}")
def get_run(run_id: str, db: Session = Depends(get_db), _: User = Depends(any_user)):
    r = _run(db, run_id)
    out = run_out(r)
    out["decisions"] = [{"gate": d.gate, "decision": d.decision, "user": d.user_email, "comment": d.comment,
                         "at": d.at.isoformat()} for d in db.query(HitlDecision).filter_by(run_id=run_id).order_by(HitlDecision.at)]
    return out


@router.get("/{run_id}/data/{name}")
def get_data(run_id: str, name: str, limit: int = 200, offset: int = 0, db: Session = Depends(get_db), _: User = Depends(any_user)):
    if name not in ("parsed", "canonical", "enriched", "final", "lineage", "rerouted"):
        raise HTTPException(400, "unknown dataset")
    _run(db, run_id)
    if not dataset_exists(run_id, name):
        return {"rows": [], "total": 0, "headers": []}
    d = load_dataset(run_id, name)
    rows = d["rows"]
    return {"rows": rows[offset:offset + limit], "total": len(rows), "headers": d.get("headers", [])}


@router.get("/{run_id}/feed")
def get_feed(run_id: str, db: Session = Depends(get_db), _: User = Depends(any_user)):
    return operational.feed(db, run_id)


class GateIn(BaseModel):
    comment: str = ""


@router.post("/{run_id}/gates/{gate}/approve")
def approve_gate(run_id: str, gate: int, body: GateIn, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    r = _run(db, run_id)
    if r.file.hitl_gate != gate:
        raise HTTPException(409, f"Gate {gate} is not open")
    if gate == 1:   # validate synchronously so the analyst sees the error immediately
        unresolved = [m["source"] for m in r.mappings if m["status"] == "review"]
        if unresolved and not body.comment:
            raise HTTPException(422, f"{len(unresolved)} column(s) still in review ({', '.join(unresolved[:5])}). "
                                     "Correct them or add a comment to approve as-is.")
    r.file.status = "running"
    db.commit()
    get_queue().enqueue({"type": "approve", "run_id": run_id, "gate": gate, "user": user.email, "comment": body.comment})
    return {"queued": True}


@router.post("/{run_id}/gates/{gate}/reject")
def reject_gate(run_id: str, gate: int, body: GateIn, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    try:
        return orchestrator.reject(db, run_id, gate, user.email, body.comment)
    except orchestrator.PipelineError as e:
        raise HTTPException(409, str(e))


class MappingIn(BaseModel):
    canonical: str | None = None
    formula: dict | None = None    # {"colA","op","colB","target"}


@router.put("/{run_id}/mappings/{index}")
def edit_mapping(run_id: str, index: int, body: MappingIn, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    try:
        return orchestrator.update_mapping(db, run_id, index, user.email, body.canonical, body.formula)
    except orchestrator.PipelineError as e:
        raise HTTPException(409, str(e))


class ExcIn(BaseModel):
    action: str   # accept | exclude | reopen
    note: str = ""


@router.post("/{run_id}/exceptions/{exc_id}")
def act_exception(run_id: str, exc_id: str, body: ExcIn, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    if body.action not in ("accept", "exclude", "reopen"):
        raise HTTPException(400, "action must be accept | exclude | reopen")
    try:
        e = orchestrator.resolve_exception(db, run_id, exc_id, body.action, user.email, body.note)
    except orchestrator.PipelineError as err:
        raise HTTPException(409, str(err))
    return {"id": e.id, "status": e.status}


@router.post("/{run_id}/dua-email")
def draft_email(run_id: str, body: GateIn, db: Session = Depends(get_db), user: User = Depends(analyst_only)):
    r = _run(db, run_id)
    ctx = AgentContext(db=db, file=r.file, run=r, settings=get_pipeline_settings(db), user_email=user.email)
    text = ReportingAgent(ctx).dua_email("corrections requested", body.comment)
    db.commit()
    return {"draft": text}


class AskIn(BaseModel):
    question: str


@router.post("/{run_id}/ask")
def ask(run_id: str, body: AskIn, db: Session = Depends(get_db), _: User = Depends(any_user)):
    r = _run(db, run_id)
    answer = ask_file(db, r, body.question)
    operational.record(db, "Insights Agent", "File question answered", body.question[:200], run_id=run_id, file_id=r.file_id)
    db.commit()
    return {"answer": answer}


@router.get("/{run_id}/export.csv", response_class=PlainTextResponse)
def export(run_id: str, db: Session = Depends(get_db), _: User = Depends(any_user)):
    r = _run(db, run_id)
    if not dataset_exists(run_id, "final"):
        raise HTTPException(404, "Final dataset not built yet")
    csv_text = export_csv(load_dataset(run_id, "final")["rows"])
    name = "LCRS_" + r.file.filename.rsplit(".", 1)[0] + ".csv"
    return PlainTextResponse(csv_text, media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'})
