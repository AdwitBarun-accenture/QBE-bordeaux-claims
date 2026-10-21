"""Settings an analyst can change in the UI (Settings page): confidence
thresholds, HITL gates and processing options. Stored in the DB, defaults from env."""
from copy import deepcopy

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AppSetting

KEY = "pipeline"


def defaults() -> dict:
    s = get_settings()
    return {
        "auto_approve_threshold": s.auto_approve_threshold,
        "review_threshold": s.review_threshold,
        "freetext_merge_threshold": s.freetext_merge_threshold,
        "gates": {"mapping": True, "exceptions": True, "load": True},
        "processing": {
            "multi_sheet_detection": True,
            "structural_change_detection": True,
            "dedup_check": True,
            "ai_anomaly_detection": True,
            "freetext_extraction": True,
        },
        "brokerage_cap_percent": 15.0,
        "da_watch_percent": 75.0,
        "da_alert_percent": 90.0,
        "sla_day_of_month": 15,
        "quality_weights": {"completeness": 1.0, "accuracy": 1.0, "consistency": 1.0},
    }


def _merge(base: dict, override: dict) -> dict:
    out = deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def get_pipeline_settings(db: Session) -> dict:
    row = db.get(AppSetting, KEY)
    return _merge(defaults(), row.value if row else {})


def update_pipeline_settings(db: Session, patch: dict) -> dict:
    current = get_pipeline_settings(db)
    new = _merge(current, patch)
    row = db.get(AppSetting, KEY)
    if row:
        row.value = new
    else:
        db.add(AppSetting(key=KEY, value=new))
    db.commit()
    return new
