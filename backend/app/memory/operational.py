"""Operational memory: append-only audit trail of every agent action, HITL
decision and LLM call (with tokens) - powers the 'Agent Activity' feed and
cost governance."""
from sqlalchemy.orm import Session

from app.db.models import OperationalLog
from app.utils.logging import get_correlation_id, get_logger

log = get_logger("audit")


def record(db: Session, agent: str, action: str, detail: str = "", *, run_id: str = "", file_id: str = "",
           level: str = "info", model: str = "", input_tokens: int = 0, output_tokens: int = 0, duration_ms: int = 0) -> None:
    db.add(OperationalLog(correlation_id=get_correlation_id(), run_id=run_id, file_id=file_id, agent=agent,
                          action=action, detail=detail, level=level, model=model, input_tokens=input_tokens,
                          output_tokens=output_tokens, duration_ms=duration_ms))
    db.flush()
    log.info(f"[{agent}] {action}", extra={"extra_data": {"run_id": run_id, "detail": detail[:300], "tokens_in": input_tokens, "tokens_out": output_tokens}})


def feed(db: Session, run_id: str, limit: int = 100) -> list[dict]:
    rows = (db.query(OperationalLog).filter(OperationalLog.run_id == run_id)
            .order_by(OperationalLog.id.desc()).limit(limit).all())
    return [{"at": r.at.isoformat(), "agent": r.agent, "action": r.action, "detail": r.detail, "level": r.level,
             "model": r.model, "tokens": r.input_tokens + r.output_tokens, "duration_ms": r.duration_ms,
             "correlation_id": r.correlation_id} for r in rows]


def recent(db: Session, limit: int = 50) -> list[dict]:
    rows = db.query(OperationalLog).order_by(OperationalLog.id.desc()).limit(limit).all()
    return [{"at": r.at.isoformat(), "agent": r.agent, "action": r.action, "run_id": r.run_id,
             "tokens": r.input_tokens + r.output_tokens, "model": r.model, "correlation_id": r.correlation_id} for r in rows]


def token_usage(db: Session) -> dict:
    from sqlalchemy import func
    q = db.query(OperationalLog.agent, func.sum(OperationalLog.input_tokens), func.sum(OperationalLog.output_tokens),
                 func.count(OperationalLog.id)).group_by(OperationalLog.agent).all()
    return {a: {"input_tokens": int(i or 0), "output_tokens": int(o or 0), "events": n} for a, i, o, n in q}
