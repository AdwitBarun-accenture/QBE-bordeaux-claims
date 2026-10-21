import hashlib


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def headers_signature(headers: list[str]) -> str:
    """Stable fingerprint of a file layout, used for structural-change detection."""
    return hashlib.sha1("|".join(h.strip().lower() for h in headers).encode()).hexdigest()[:12]
