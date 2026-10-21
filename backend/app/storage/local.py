import os
from pathlib import Path

from app.storage.base import BlobStore, ImmutableBlobError


class LocalBlobStore(BlobStore):
    def __init__(self, root: str):
        self.root = Path(root)
        (self.root / "raw").mkdir(parents=True, exist_ok=True)
        (self.root / "staged").mkdir(parents=True, exist_ok=True)

    def _p(self, area: str, key: str) -> Path:
        p = (self.root / area / key).resolve()
        if not str(p).startswith(str((self.root / area).resolve())):
            raise ValueError("path traversal rejected")
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def put_raw(self, key: str, data: bytes) -> str:
        p = self._p("raw", key)
        if p.exists():
            raise ImmutableBlobError(f"raw blob already exists: {key}")
        p.write_bytes(data)
        os.chmod(p, 0o444)  # read-only on disk
        return f"file://{p}"

    def get_raw(self, key: str) -> bytes:
        return self._p("raw", key).read_bytes()

    def put_staged(self, key: str, data: bytes) -> str:
        p = self._p("staged", key)
        p.write_bytes(data)
        return f"file://{p}"

    def get_staged(self, key: str) -> bytes:
        return self._p("staged", key).read_bytes()

    def exists_staged(self, key: str) -> bool:
        return self._p("staged", key).exists()
