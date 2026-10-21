"""Job handlers. Long-running agent work never runs inside the HTTP request:
the API enqueues a job and the UI polls the file/run status."""
from app.agents import orchestrator
from app.db.models import BdxFile, PipelineRun
from app.db.session import session_scope
from app.memory import operational
from app.utils.logging import get_logger

log = get_logger(__name__)


def _mark_failed(file_id: str | None, run_id: str | None, err: Exception) -> None:
    with session_scope() as db:
        f = db.get(BdxFile, file_id) if file_id else None
        r = db.get(PipelineRun, run_id) if run_id else None
        if r and not f:
            f = r.file
        if f:
            f.status, f.error = "failed", f"{type(err).__name__}: {err}"[:2000]
        if r:
            r.status = "failed"
        operational.record(db, "System", "Job failed", str(err)[:1000], run_id=run_id or "", file_id=file_id or "", level="error")


def execute(job: dict) -> None:
    kind = job["type"]
    try:
        with session_scope() as db:
            if kind == "start":
                orchestrator.start(db, job["file_id"], password=job.get("password"),
                                   remember_password=job.get("remember", False), sheet=job.get("sheet"), user=job.get("user", "system"))
            elif kind == "approve":
                orchestrator.approve(db, job["run_id"], job["gate"], job["user"], job.get("comment", ""))
            else:
                raise ValueError(f"unknown job type {kind}")
    except orchestrator.PipelineError as e:
        log.warning(f"pipeline rejected job {kind}: {e}")
        _mark_failed(job.get("file_id"), job.get("run_id"), e) if kind == "start" else None
    except Exception as e:
        log.exception(f"job {kind} failed")
        _mark_failed(job.get("file_id"), job.get("run_id"), e)
