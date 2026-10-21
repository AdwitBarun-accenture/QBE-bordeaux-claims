import os
import shutil
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = tempfile.mkdtemp(prefix="bdx-test-")
os.environ.update({
    "DATABASE_URL": f"sqlite:///{TMP}/app.db",
    "DWH_DATABASE_URL": f"sqlite:///{TMP}/dwh.db",
    "LOCAL_STORAGE_ROOT": f"{TMP}/data",
    "LLM_PROVIDER": "none",
    "QUEUE_BACKEND": "sync",
    "ENABLE_SCHEDULER": "false",
})
from cryptography.fernet import Fernet  # noqa: E402
os.environ["LOCAL_VAULT_KEY"] = Fernet.generate_key().decode()

SAMPLES = ROOT.parent / "sample_data"


@pytest.fixture(scope="session")
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c
    shutil.rmtree(TMP, ignore_errors=True)


@pytest.fixture(scope="session")
def auth(client):
    tok = client.post("/api/auth/login", json={"email": "analyst@lloyds.com", "password": "demo"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def uw_auth(client):
    tok = client.post("/api/auth/login", json={"email": "underwriter@lloyds.com", "password": "demo"}).json()["token"]
    return {"Authorization": f"Bearer {tok}"}
