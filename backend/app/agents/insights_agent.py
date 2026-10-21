"""Insights Agent - portfolio analytics + conversational Q&A.

Mockup: every number came from a hard-coded SYN object, and the chat prompt
was given those fake numbers. Here the dashboard is computed from the warehouse
(loaded LCRS records), coverholder profiles, episodic memory and exception history,
and the Q&A is grounded on that computed context only (no free SQL generation).
"""
from collections import defaultdict

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.runtime_settings import get_pipeline_settings
from app.db.models import BdxFile, Coverholder, DataException, EpisodicMemory, PipelineRun
from app.llm.base import LLMUnavailable
from app.llm.client import LLMClient
from app.llm.prompts import insights as P
from app.loaders.factory import get_warehouse
from app.memory import operational
from app.utils.json_utils import dumps


def dashboard(db: Session) -> dict:
    s = get_pipeline_settings(db)
    p = get_warehouse().portfolio() or {}
    written = defaultdict(float)
    for x in p.get("written_by_coverholder", []):
        written[x["coverholder"]] += x["gbp"]
    da = []
    for ch in db.query(Coverholder).all():
        if ch.da_limit_gbp:
            pct = round(written[ch.name] / ch.da_limit_gbp * 100)
            da.append({"coverholder": ch.name, "class": ch.class_of_business, "limit_gbp": ch.da_limit_gbp,
                       "written_gbp": round(written[ch.name], 2), "utilisation": pct,
                       "status": "approaching" if pct >= s["da_alert_percent"] else "watch" if pct >= s["da_watch_percent"] else "ok"})
    quality = defaultdict(list)
    for e in db.query(EpisodicMemory).order_by(EpisodicMemory.at).all():
        quality[e.coverholder_name].append({"at": e.at.date().isoformat(), "quality": e.quality, "exceptions": e.exception_count})
    patterns = (db.query(DataException.title, func.count(DataException.id), func.max(PipelineRun.started_at))
                .join(PipelineRun, PipelineRun.id == DataException.run_id)
                .group_by(DataException.title).order_by(func.count(DataException.id).desc()).limit(10).all())
    pattern_rows = []
    for title, n, last in patterns:
        chs = (db.query(BdxFile.coverholder_name).join(PipelineRun, PipelineRun.file_id == BdxFile.id)
               .join(DataException, DataException.run_id == PipelineRun.id).filter(DataException.title == title).distinct().all())
        pattern_rows.append({"exception": title, "count": n, "coverholders": [c for (c,) in chs][:5],
                             "last_seen": last.date().isoformat() if last else None})
    open_exc = db.query(func.count(DataException.id)).filter(DataException.status == "open").scalar()
    open_hi = db.query(func.count(DataException.id)).filter(DataException.status == "open", DataException.severity == "high").scalar()
    avg_q = db.query(func.avg(BdxFile.quality)).filter(BdxFile.status == "processed").scalar()
    return {
        "kpis": {"gwp_gbp": round(p.get("gwp_gbp", 0), 2), "files_loaded": p.get("files", 0),
                 "files_received": db.query(func.count(BdxFile.id)).scalar(), "avg_quality": round(avg_q or 0),
                 "open_exceptions": open_exc, "open_high": open_hi},
        "gwp_by_cob": p.get("gwp_by_cob", []), "files_by_month": p.get("files_by_month", []),
        "da_utilisation": sorted(da, key=lambda x: -x["utilisation"]),
        "claims_by_coverholder": p.get("claims_by_coverholder", []),
        "quality_trend": [{"coverholder": k, "points": v[-6:]} for k, v in quality.items()],
        "exception_patterns": pattern_rows,
        "token_usage": operational.token_usage(db),
    }


def ask_portfolio(db: Session, question: str) -> str:
    ctx = dashboard(db)
    ctx.pop("token_usage", None)
    try:
        return LLMClient().text("portfolio Q&A", P.SYSTEM, P.portfolio_question(dumps(ctx), question), 400).text
    except LLMUnavailable:
        k = ctx["kpis"]
        return (f"AI is not configured, so here are the headline figures: GWP GBP {k['gwp_gbp']:,.0f} across "
                f"{k['files_loaded']} loaded files, average quality {k['avg_quality']}%, {k['open_exceptions']} open exceptions "
                f"({k['open_high']} high). Set LLM_PROVIDER to enable conversational answers.")


def ask_file(db: Session, run: PipelineRun, question: str) -> str:
    f = run.file
    ctx = {"file": f.filename, "coverholder": f.coverholder_name, "type": f.file_type, "status": f.status,
           "ingestion": {k: run.ingestion.get(k) for k in ("records", "columns", "format", "sheet", "warnings", "missing_mandatory")},
           "mappings": [{k: m[k] for k in ("source", "canonical", "confidence", "status")} for m in run.mappings],
           "scores": run.validation.get("scores"),
           "exceptions": [{"title": e.title, "severity": e.severity, "count": e.count, "rows": e.row_indexes[:10],
                           "status": e.status, "suggestion": e.suggestion} for e in run.exceptions],
           "enrichment": run.enrichment.get("steps"), "reconciliation": run.reconciliation.get("checks"),
           "freetext": (run.freetext.get("results") or [])[:10]}
    try:
        return LLMClient().text("file Q&A", P.SYSTEM, P.file_question(dumps(ctx), question), 350).text
    except LLMUnavailable:
        hi = [e.title for e in run.exceptions if e.severity == "high" and e.status == "open"]
        return (f"{f.filename}: {run.ingestion.get('records')} records, quality {run.validation.get('scores', {}).get('overall')}%, "
                f"{len(run.exceptions)} exceptions" + (f" (high: {', '.join(hi)})" if hi else "") + ". Enable an LLM provider for free-form answers.")
