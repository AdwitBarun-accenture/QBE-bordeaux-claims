from datetime import datetime, timezone

from app.db.models import BdxFile, PipelineRun


def file_out(f: BdxFile) -> dict:
    sla_days = None
    if f.sla_due:
        due = f.sla_due if f.sla_due.tzinfo else f.sla_due.replace(tzinfo=timezone.utc)
        sla_days = (due.date() - datetime.now(timezone.utc).date()).days
    return {"id": f.id, "coverholder": f.coverholder_name, "filename": f.filename, "file_type": f.file_type,
            "source": f.source, "received_at": f.received_at.isoformat() if f.received_at else None,
            "status": f.status, "hitl_gate": f.hitl_gate, "records": f.record_count, "quality": f.quality,
            "sla_days": sla_days, "password_protected": f.password_protected, "error": f.error,
            "latest_run_id": f.latest_run_id}


def run_out(r: PipelineRun) -> dict:
    return {"id": r.id, "file": file_out(r.file), "correlation_id": r.correlation_id, "stage": r.stage, "status": r.status,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "ingestion": r.ingestion, "mappings": r.mappings, "structural_change": r.structural_change,
            "validation": r.validation, "enrichment": {k: v for k, v in (r.enrichment or {}).items() if k != "lineage_sample"},
            "freetext": r.freetext, "reconciliation": r.reconciliation, "summary": r.summary,
            "resolution_guidance": r.resolution_guidance, "load_result": r.load_result,
            "exceptions": [{"id": e.id, "rule_id": e.rule_id, "title": e.title, "severity": e.severity, "count": e.count,
                            "rows": e.row_indexes, "suggestion": e.suggestion, "source": e.source, "status": e.status,
                            "resolved_by": e.resolved_by, "note": e.resolution_note} for e in r.exceptions]}
