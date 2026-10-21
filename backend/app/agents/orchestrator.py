"""Pipeline orchestrator - the state machine that runs the agents and the
three Human-in-the-Loop (HITL) gates.

    received ──► [01 Ingestion] ──► [02 Mapping] ──► GATE 1 Mapping sign-off
                     │ password?                         │ approve (memory learns)
                     ▼                                    ▼
             awaiting-password          [03 Validation] → [04 Cleansing] → [05 Classification]
                                                          → [06 Reporting.prepare]
                                                                  │
                                                       GATE 2 Exception review
                                                                  │ approve
                                                       [06 Reporting.prepare] (exclusions applied)
                                                                  │
                                                       GATE 3 DWH load sign-off
                                                                  │ approve
                                                       [06 Reporting.load] → processed
                                                       (episodic memory saved)
    Any gate: reject -> status 'rejected' + DUA email draft + episodic record.

A gate is skipped automatically ('auto' decision recorded) when it is disabled
in Settings AND nothing needs a human (e.g. all mappings >= threshold).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.base import AgentContext
from app.agents.classification_agent import ClassificationAgent
from app.agents.cleansing_agent import CleansingAgent
from app.agents.ingestion_agent import AwaitingPassword, IngestionAgent, IngestionFailed
from app.agents.mapping_agent import MappingAgent, status_for
from app.agents.reporting_agent import ReportingAgent
from app.agents.validation_agent import ValidationAgent
from app.core.lcrs_schema import mandatory_fields
from app.core.runtime_settings import get_pipeline_settings
from app.db.models import BdxFile, DataException, HitlDecision, PipelineRun
from app.mapping.formula import validate_formula
from app.memory import episodic, operational, semantic
from app.storage.factory import load_dataset
from app.utils.logging import new_correlation_id, set_correlation_id

GATE_STATUS = {1: "awaiting-mapping", 2: "awaiting-exceptions", 3: "awaiting-load"}
GATE_NAME = {1: "Mapping sign-off", 2: "Exception review", 3: "DWH load sign-off"}
GATE_KEY = {1: "mapping", 2: "exceptions", 3: "load"}


class PipelineError(Exception):
    pass


def _ctx(db: Session, f: BdxFile, run: PipelineRun, user: str = "system") -> AgentContext:
    set_correlation_id(run.correlation_id)
    return AgentContext(db=db, file=f, run=run, settings=get_pipeline_settings(db), user_email=user)


def _hydrate(ctx: AgentContext) -> None:
    """Resume after a gate (new HTTP request / worker): reload datasets from storage."""
    rid = ctx.run.id
    if "parsed" not in ctx.cache:
        d = load_dataset(rid, "parsed")
        ctx.cache["parsed"], ctx.cache["headers"] = d["rows"], d["headers"]
    for name in ("canonical", "enriched", "final"):
        if name not in ctx.cache:
            try:
                ctx.cache[name] = load_dataset(rid, name)["rows"]
            except Exception:
                pass


def _open_gate(ctx: AgentContext, gate: int, reason: str) -> None:
    ctx.file.status, ctx.file.hitl_gate = GATE_STATUS[gate], gate
    ctx.run.status = GATE_STATUS[gate]
    operational.record(ctx.db, "System", f"Gate {gate} opened: {GATE_NAME[gate]}", reason, run_id=ctx.run.id,
                       file_id=ctx.file.id, level="hitl")


def _auto_pass(ctx: AgentContext, gate: int, reason: str) -> None:
    ctx.db.add(HitlDecision(run_id=ctx.run.id, gate=gate, decision="auto", user_email="system", comment=reason))
    operational.record(ctx.db, "System", f"Gate {gate} auto-passed", reason, run_id=ctx.run.id, file_id=ctx.file.id)


# =========================================================== entry points
def start(db: Session, file_id: str, password: str | None = None, remember_password: bool = False,
          sheet: str | None = None, user: str = "system") -> PipelineRun:
    f = db.get(BdxFile, file_id)
    if not f:
        raise PipelineError("file not found")
    if f.status == "duplicate":
        raise PipelineError("duplicate file - not processed")
    run = PipelineRun(file_id=f.id, correlation_id=new_correlation_id())
    db.add(run)
    db.flush()
    f.latest_run_id, f.status, f.hitl_gate, f.error = run.id, "running", None, ""
    ctx = _ctx(db, f, run, user)
    db.commit()
    try:
        IngestionAgent(ctx).run(password=password, remember_password=remember_password, sheet=sheet)
        run.stage = "ingest"
        db.commit()
        mapper = MappingAgent(ctx)
        mapper.run()
        run.stage = "map"
        if mapper.needs_review() or ctx.settings["gates"]["mapping"]:
            reasons = []
            if any(m["status"] == "review" for m in run.mappings):
                reasons.append(f"{sum(m['status'] == 'review' for m in run.mappings)} column(s) need review")
            if run.ingestion.get("missing_mandatory"):
                reasons.append("mandatory fields unmapped")
            if run.structural_change.get("changed"):
                reasons.append("layout changed since last submission")
            _open_gate(ctx, 1, "; ".join(reasons) or "mapping sign-off is mandatory (Settings)")
        else:
            _auto_pass(ctx, 1, "all columns >= auto-approve threshold, gate disabled")
            _after_mapping(ctx)
        db.commit()
    except AwaitingPassword:
        run.status = "awaiting-password"
        db.commit()
    except IngestionFailed as e:
        run.status, f.status, f.error = "failed", "failed", str(e)
        db.commit()
    except Exception as e:
        db.rollback()
        f = db.get(BdxFile, file_id)
        run = db.get(PipelineRun, run.id)
        f.status, f.error, run.status = "failed", f"Pipeline error: {e}", "failed"
        operational.record(db, "System", "Pipeline failed", str(e)[:1000], run_id=run.id, file_id=f.id, level="error")
        db.commit()
        raise
    return run


def _after_mapping(ctx: AgentContext) -> None:
    _hydrate(ctx)
    ValidationAgent(ctx).run()
    ctx.run.stage = "validate"
    CleansingAgent(ctx).run()
    ctx.run.stage = "cleanse"
    ClassificationAgent(ctx).run()
    ctx.run.stage = "freetext"
    ReportingAgent(ctx).prepare()
    ctx.run.stage = "reconcile"
    open_exc = [e for e in ctx.run.exceptions if e.status == "open"]
    if open_exc or ctx.settings["gates"]["exceptions"]:
        hi = sum(e.severity == "high" for e in open_exc)
        _open_gate(ctx, 2, f"{len(open_exc)} open exception(s), {hi} high severity")
    else:
        _auto_pass(ctx, 2, "no exceptions, gate disabled")
        _after_exceptions(ctx)


def _after_exceptions(ctx: AgentContext) -> None:
    _hydrate(ctx)
    ReportingAgent(ctx).prepare()   # re-run with analyst's exclusions/acceptances
    if ctx.settings["gates"]["load"]:
        _open_gate(ctx, 3, f"{ctx.run.reconciliation.get('to_load')} records ready; approve to commit")
    else:
        _auto_pass(ctx, 3, "load gate disabled")
        _load(ctx)


def _load(ctx: AgentContext) -> None:
    res = ReportingAgent(ctx).load()
    f, run = ctx.file, ctx.run
    if not res.get("verified"):
        f.status, run.status, f.error = "failed", "failed", "Load verification failed"
        return
    f.status, f.hitl_gate, run.status, run.stage = "processed", None, "processed", "load"
    f.record_count = run.reconciliation.get("received", f.record_count)
    run.finished_at = datetime.now(timezone.utc)
    _save_episode(ctx, "loaded")


def _save_episode(ctx: AgentContext, outcome: str) -> None:
    run, f = ctx.run, ctx.file
    decisions = {f"gate{d.gate}": d.decision for d in ctx.db.query(HitlDecision).filter_by(run_id=run.id).all()}
    episodic.save(ctx.db, coverholder=f.coverholder_name, file_type=f.file_type, file_id=f.id, run_id=run.id,
                  filename=f.filename, headers=run.ingestion.get("headers", []),
                  quality=run.validation.get("scores", {}).get("overall", 0),
                  exceptions=[e.title for e in run.exceptions], hitl=decisions, outcome=outcome)
    operational.record(ctx.db, "System", "Episodic memory updated", f"outcome: {outcome}", run_id=run.id, file_id=f.id)


# =========================================================== HITL actions
def _get(db: Session, run_id: str, user: str) -> AgentContext:
    run = db.get(PipelineRun, run_id)
    if not run:
        raise PipelineError("run not found")
    return _ctx(db, run.file, run, user)


def approve(db: Session, run_id: str, gate: int, user: str, comment: str = "") -> PipelineRun:
    ctx = _get(db, run_id, user)
    if ctx.file.hitl_gate != gate:
        raise PipelineError(f"Gate {gate} is not open (current: {ctx.file.hitl_gate})")
    if gate == 1:
        unresolved = [m["source"] for m in ctx.run.mappings if m["status"] == "review"]
        missing = [x for x in mandatory_fields(ctx.file.file_type)
                   if x not in {m["canonical"] for m in ctx.run.mappings if m["status"] != "unmapped"}
                   | {m["formula"]["target"] for m in ctx.run.mappings if m.get("formula")}]
        if unresolved and not comment:
            raise PipelineError(f"{len(unresolved)} column(s) still in review: {', '.join(unresolved[:5])}. "
                                "Confirm/correct them or add a comment to approve as-is.")
    db.add(HitlDecision(run_id=run_id, gate=gate, decision="approved", user_email=user, comment=comment))
    operational.record(db, f"HITL Gate {gate}", f"{GATE_NAME[gate]} approved by {user}", comment, run_id=run_id,
                       file_id=ctx.file.id, level="hitl")
    ctx.file.hitl_gate = None
    if gate == 1:
        n = semantic.remember(db, ctx.file.coverholder_name, ctx.file.file_type, ctx.run.mappings, user,
                              ctx.settings["auto_approve_threshold"])
        operational.record(db, "Mapping Agent", "Semantic memory updated", f"{n} new pair(s) stored for {ctx.file.coverholder_name}",
                           run_id=run_id, file_id=ctx.file.id)
        if missing:
            operational.record(db, "System", "Approved with unmapped mandatory fields", ", ".join(missing),
                               run_id=run_id, file_id=ctx.file.id, level="warn")
        ctx.file.status = "running"
        db.commit()
        _after_mapping(ctx)
    elif gate == 2:
        for e in ctx.run.exceptions:
            if e.status == "open":
                # claims rows found inside a premium file are routed out, not loaded,
                # unless the analyst explicitly accepted that exception
                e.status = "rerouted" if e.rule_id == "MIXED_TYPES" else "accepted"
                e.resolved_by, e.resolution_note = user, "approved at exception review"
        db.flush()
        _after_exceptions(ctx)
    elif gate == 3:
        _load(ctx)
    db.commit()
    return ctx.run


def reject(db: Session, run_id: str, gate: int, user: str, comment: str = "") -> dict:
    ctx = _get(db, run_id, user)
    if ctx.file.hitl_gate != gate:
        raise PipelineError(f"Gate {gate} is not open")
    db.add(HitlDecision(run_id=run_id, gate=gate, decision="rejected", user_email=user, comment=comment))
    operational.record(db, f"HITL Gate {gate}", f"{GATE_NAME[gate]} rejected by {user}", comment, run_id=run_id,
                       file_id=ctx.file.id, level="hitl")
    email = ReportingAgent(ctx).dua_email("rejected - resubmission required", comment)
    ctx.file.status, ctx.file.hitl_gate, ctx.run.status = "rejected", None, "rejected"
    ctx.run.finished_at = datetime.now(timezone.utc)
    _save_episode(ctx, "rejected")
    db.commit()
    return {"status": "rejected", "dua_email_draft": email}


def update_mapping(db: Session, run_id: str, index: int, user: str, canonical: str | None = None,
                   formula: dict | None = None) -> list[dict]:
    """Analyst edits a mapping at Gate 1 (dropdown or formula modal)."""
    ctx = _get(db, run_id, user)
    if ctx.file.hitl_gate != 1:
        raise PipelineError("Mappings can only be edited while Gate 1 is open")
    mappings = [dict(m) for m in ctx.run.mappings]
    if not 0 <= index < len(mappings):
        raise PipelineError("bad mapping index")
    m = mappings[index]
    before = m.get("canonical")
    if formula:
        err = validate_formula(formula, ctx.run.ingestion.get("headers", []))
        if err:
            raise PipelineError(err)
        m.update(formula=formula, canonical=formula["target"], confidence=100, human_corrected=False, origin="formula",
                 notes=f"formula: {formula['colA']} {formula['op']} {formula['colB']}")
    else:
        m.update(canonical=canonical or "unmapped", confidence=100 if canonical and canonical != "unmapped" else 0,
                 human_corrected=True, formula=None, origin="human", notes="human corrected")
        if m["canonical"] != "unmapped":   # keep one source per target
            for other in mappings:
                if other is not m and other.get("canonical") == m["canonical"] and not other.get("formula"):
                    other.update(canonical="unmapped", confidence=0, notes=f"replaced by '{m['source']}'")
    s = ctx.settings
    for x in mappings:
        x["status"] = status_for(x, s["auto_approve_threshold"], s["review_threshold"])
    ctx.run.mappings = mappings
    operational.record(db, "Analyst", "Mapping corrected", f"{m['source']}: {before} -> {m['canonical']}",
                       run_id=run_id, file_id=ctx.file.id)
    db.commit()
    return mappings


def resolve_exception(db: Session, run_id: str, exc_id: str, action: str, user: str, note: str = "") -> DataException:
    """action: accept (load rows flagged) | exclude (keep rows out of the load) | reopen"""
    ctx = _get(db, run_id, user)
    if ctx.file.hitl_gate not in (2, 3):
        raise PipelineError("Exceptions can be actioned at Gate 2 or 3")
    e = db.get(DataException, exc_id)
    if not e or e.run_id != run_id:
        raise PipelineError("exception not found")
    e.status = {"accept": "accepted", "exclude": "excluded", "reopen": "open"}[action]
    e.resolved_by, e.resolution_note, e.resolved_at = user, note, datetime.now(timezone.utc)
    operational.record(db, "Analyst", f"Exception {e.status}", f"{e.title} ({e.count} rows). {note}", run_id=run_id, file_id=ctx.file.id)
    db.flush()
    if ctx.file.hitl_gate == 3:   # refresh final dataset immediately
        _hydrate(ctx)
        ReportingAgent(ctx).prepare()
    db.commit()
    return e
