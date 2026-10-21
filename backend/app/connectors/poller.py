"""Pull new files from every configured connector -> intake -> enqueue pipeline."""
from app.core.runtime_settings import get_pipeline_settings
from app.db.models import ConnectorState
from app.db.session import session_scope
from app.services.intake import receive_file
from app.utils.logging import get_logger
from app.workers.queue import get_queue

log = get_logger(__name__)


def _connectors():
    out = []
    try:
        from app.connectors.email_graph import GraphMailbox
        out.append(("email", GraphMailbox()))
    except RuntimeError as e:
        log.info(str(e))
    try:
        from app.connectors.sftp import SftpWatcher
        out.append(("sftp", SftpWatcher()))
    except RuntimeError as e:
        log.info(str(e))
    return out


def poll_connectors() -> dict:
    summary = {}
    for name, conn in _connectors():
        with session_scope() as db:
            seen = {s.external_id for s in db.query(ConnectorState).filter_by(connector=name).all()}
        try:
            files = conn.fetch_new(seen)
        except Exception as e:
            log.exception(f"{name} poll failed")
            summary[name] = f"error: {e}"
            continue
        n = 0
        for inc in files:
            with session_scope() as db:
                sla_day = get_pipeline_settings(db)["sla_day_of_month"]
                f = receive_file(db, filename=inc.filename, data=inc.data, source=inc.source, source_ref=inc.source_ref,
                                 sender=inc.sender, sla_day=sla_day)
                db.add(ConnectorState(connector=name, external_id=inc.external_id))
                fid, status = f.id, f.status
            if status == "received":
                get_queue().enqueue({"type": "start", "file_id": fid})
            if name == "sftp":
                try:
                    conn.archive(inc.source_ref)
                except Exception:
                    log.warning(f"could not archive {inc.source_ref}")
            n += 1
        summary[name] = n
    return summary
