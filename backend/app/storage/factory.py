import json
from functools import lru_cache

from app.core.config import get_settings
from app.storage.base import BlobStore
from app.utils.json_utils import dumps


@lru_cache
def get_store() -> BlobStore:
    s = get_settings()
    if s.storage_backend == "azure_blob":
        from app.storage.azure_blob import AzureBlobStore
        return AzureBlobStore(s.azure_storage_account_url, s.azure_storage_connection_string,
                              s.azure_raw_container, s.azure_staged_container)
    from app.storage.local import LocalBlobStore
    return LocalBlobStore(s.local_storage_root)


# ---- dataset helpers (rows are list[dict]) ----
def save_dataset(run_id: str, name: str, rows: list[dict], extra: dict | None = None) -> str:
    payload = {"rows": rows, **(extra or {})}
    return get_store().put_staged(f"{run_id}/{name}.json", dumps(payload).encode())


def load_dataset(run_id: str, name: str) -> dict:
    return json.loads(get_store().get_staged(f"{run_id}/{name}.json"))


def dataset_exists(run_id: str, name: str) -> bool:
    return get_store().exists_staged(f"{run_id}/{name}.json")
