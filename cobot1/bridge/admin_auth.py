"""관리자 세션 인증."""

from __future__ import annotations

import os
import secrets
import time

SESSION_TTL_SEC = 8 * 3600
_sessions: dict[str, float] = {}


def admin_password() -> str:
    return os.environ.get("COBOT1_ADMIN_PASSWORD", "admin")


def verify_password(password: str) -> bool:
    return password == admin_password()


def create_session() -> str:
    _purge_expired()
    token = secrets.token_urlsafe(32)
    _sessions[token] = time.time() + SESSION_TTL_SEC
    return token


def validate_session(token: str | None) -> bool:
    if not token:
        return False
    _purge_expired()
    expires = _sessions.get(token)
    if expires is None:
        return False
    if time.time() > expires:
        _sessions.pop(token, None)
        return False
    return True


def revoke_session(token: str | None) -> None:
    if token:
        _sessions.pop(token, None)


def _purge_expired() -> None:
    now = time.time()
    expired = [k for k, v in _sessions.items() if now > v]
    for key in expired:
        _sessions.pop(key, None)
