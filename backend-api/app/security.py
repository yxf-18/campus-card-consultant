from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import jwt

from .config import get_settings

settings = get_settings()
_revoked: dict[str, float] = {}
_revoke_lock = Lock()


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$16384$8$1$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(expected, actual)
    except (ValueError, TypeError):
        return False


def create_access_token(user_id: int, username: str, role: str) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_in = settings.jwt_expires_seconds
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=expires_in)).timestamp()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm="HS256")
    return token, expires_in


def decode_access_token(token: str) -> dict[str, Any]:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("invalid token type")
    jti = str(payload.get("jti", ""))
    with _revoke_lock:
        if jti in _revoked:
            raise jwt.InvalidTokenError("token revoked")
    return payload


def revoke_token(payload: dict[str, Any]) -> None:
    jti = str(payload.get("jti", ""))
    exp = float(payload.get("exp", time.time() + 3600))
    with _revoke_lock:
        now = time.time()
        for key in [k for k, value in _revoked.items() if value <= now]:
            _revoked.pop(key, None)
        if jti:
            _revoked[jti] = exp


def create_download_token(kind: str, object_id: int | str, expires_seconds: int = 300) -> str:
    payload = {
        "sub": str(object_id),
        "kind": kind,
        "exp": int(time.time()) + expires_seconds,
        "nonce": secrets.token_hex(4),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_download_token(token: str, expected_kind: str) -> str:
    payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    if payload.get("kind") != expected_kind:
        raise jwt.InvalidTokenError("wrong download kind")
    return str(payload.get("sub"))
