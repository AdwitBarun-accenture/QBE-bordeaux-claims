"""Blob storage abstraction.

raw/    : original files exactly as received - WRITE ONCE (immutable audit copy)
staged/ : parsed / canonical / final datasets per run (JSON)
"""
from abc import ABC, abstractmethod


class ImmutableBlobError(Exception):
    pass


class BlobStore(ABC):
    @abstractmethod
    def put_raw(self, key: str, data: bytes) -> str:
        """Store an original file. Must refuse to overwrite. Returns a URI."""

    @abstractmethod
    def get_raw(self, key: str) -> bytes: ...

    @abstractmethod
    def put_staged(self, key: str, data: bytes) -> str: ...

    @abstractmethod
    def get_staged(self, key: str) -> bytes: ...

    @abstractmethod
    def exists_staged(self, key: str) -> bool: ...
