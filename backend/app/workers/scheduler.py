"""Polls email + SFTP connectors every N minutes (ENABLE_SCHEDULER=true).
On Azure, run this in exactly ONE replica (or as a Container Apps Job on a cron)."""
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import get_settings
from app.utils.logging import get_logger

log = get_logger(__name__)
_scheduler = None


def poll_all() -> dict:
    from app.connectors.poller import poll_connectors
    return poll_connectors()


def start_scheduler():
    global _scheduler
    s = get_settings()
    if not s.enable_scheduler or _scheduler:
        return
    _scheduler = BackgroundScheduler()
    _scheduler.add_job(poll_all, "interval", minutes=s.poll_minutes, id="poll_connectors", max_instances=1)
    _scheduler.start()
    log.info(f"connector scheduler started (every {s.poll_minutes} min)")
