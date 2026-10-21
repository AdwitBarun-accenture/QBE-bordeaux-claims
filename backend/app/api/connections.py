from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.config import get_settings
from app.db.models import User
from app.security.auth import analyst_only

router = APIRouter(prefix="/api/connections", tags=["connections"])


@router.get("")
def status(_: User = Depends(analyst_only)):
    s = get_settings()
    return {
        "email_m365": {"configured": bool(s.graph_client_id and s.graph_mailbox), "mailbox": s.graph_mailbox},
        "email_gmail": {"configured": False, "note": "not implemented"},
        "sftp": {"configured": bool(s.sftp_host), "host": s.sftp_host, "watch_dir": s.sftp_watch_dir},
        "scheduler": {"enabled": s.enable_scheduler, "poll_minutes": s.poll_minutes},
        "warehouse": {"loader": s.dwh_loader},
        "llm": {"provider": s.llm_provider, "model": s.llm_model},
        "storage": {"backend": s.storage_backend},
        "queue": {"backend": s.queue_backend},
    }


class SftpTestIn(BaseModel):
    host: str
    port: int = 22
    username: str
    password: str
    watch_dir: str


@router.post("/sftp/test")
def sftp_test(body: SftpTestIn, _: User = Depends(analyst_only)):
    from app.connectors.sftp import SftpWatcher
    try:
        return SftpWatcher(body.host, body.port, body.username, body.password, body.watch_dir).test()
    except Exception as e:
        raise HTTPException(400, f"Connection failed: {e}")


@router.post("/poll-now")
def poll_now(_: User = Depends(analyst_only)):
    from app.connectors.poller import poll_connectors
    return poll_connectors()
