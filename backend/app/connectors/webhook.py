"""Downstream push: POST a summary to a configured webhook after each load
(e.g. to notify Lloyd's Crystal/Whitespace integration or an internal system)."""
import hashlib
import hmac
import json

import httpx


def push(url: str, secret: str, payload: dict) -> int:
    body = json.dumps(payload, default=str).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest() if secret else ""
    r = httpx.post(url, content=body, headers={"Content-Type": "application/json", "X-BDX-Signature": sig}, timeout=30)
    return r.status_code
