"""FastAPI entry point.  Local:  uvicorn app.main:app --reload"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, connections, files, insights, memory, runs, settings
from app.core.config import get_settings
from app.db.models import Coverholder
from app.db.session import init_db, session_scope
from app.security.auth import seed_demo_users
from app.utils.logging import configure_logging, new_correlation_id

DEMO_COVERHOLDERS = [  # from the mockup's CH_PROFILES
    ("Markel International", "PROP", 5_000_000, ["markel"]),
    ("CNA Hardy", "PROP/LIAB", 6_000_000, ["cna"]),
    ("Beazley", "CYBER", 2_000_000, ["beazley"]),
    ("Hiscox", "PROP", 8_000_000, ["hiscox"]),
    ("Tokio Marine HCC", "MAR", 4_000_000, ["tmhcc", "tokio"]),
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    configure_logging(s.log_level)
    init_db()
    from app.loaders.factory import get_warehouse
    get_warehouse()   # creates DWH table if needed
    with session_scope() as db:
        if s.seed_demo_users:
            seed_demo_users(db)
            for name, cls, lim, aliases in DEMO_COVERHOLDERS:
                if not db.query(Coverholder).filter_by(name=name).first():
                    db.add(Coverholder(name=name, class_of_business=cls, da_limit_gbp=lim, aliases=aliases))
    from app.workers.scheduler import start_scheduler
    start_scheduler()
    yield


app = FastAPI(title="Bordereaux Intelligence Platform API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in get_settings().cors_origins.split(",")],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def correlation(request: Request, call_next):
    cid = request.headers.get("x-correlation-id") or new_correlation_id()
    response = await call_next(request)
    response.headers["x-correlation-id"] = cid
    return response


for r in (auth, files, runs, memory, insights, settings, connections):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    s = get_settings()
    return {"ok": True, "llm_provider": s.llm_provider, "storage": s.storage_backend, "dwh": s.dwh_loader}
