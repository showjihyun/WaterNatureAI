"""인증 보안 유틸 — 비밀번호 해시(Argon2id) + JWT(access/refresh).

정본: docs/04-architecture/auth-onboarding.md §4·§7.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import settings

_ph = PasswordHasher()  # Argon2id 기본

# 로그인 타이밍 평준화용 더미 해시 — 미존재 이메일도 동일한 Argon2 검증 비용을 지불해
# 응답 시간 차로 가입 여부를 알아내는 열거(타이밍 오라클)를 차단. 모듈 로드시 1회 계산.
DUMMY_PASSWORD_HASH = _ph.hash("bizradar-timing-equalizer")


def hash_password(raw: str) -> str:
    return _ph.hash(raw)


def verify_password(stored_hash: str, raw: str) -> bool:
    try:
        return _ph.verify(stored_hash, raw)
    except VerifyMismatchError:
        return False


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(*, user_id: uuid.UUID, company_id: uuid.UUID, role: str) -> str:
    """company_id를 클레임에 포함 → 모든 조회를 company 범위로 격리."""
    exp = _now() + timedelta(minutes=settings.jwt_access_ttl_min)
    payload = {
        "sub": str(user_id),
        "company_id": str(company_id),
        "role": role,
        "type": "access",
        "exp": exp,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)


def decode_access_token(token: str) -> dict:
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_alg])


def new_refresh_token() -> tuple[str, str, datetime]:
    """(원문, 해시, 만료) — 원문은 클라이언트에, 해시만 DB 저장(회전·폐기)."""
    raw = uuid.uuid4().hex + uuid.uuid4().hex
    token_hash = hashlib.sha256(raw.encode()).hexdigest()
    expires_at = _now() + timedelta(days=settings.jwt_refresh_ttl_days)
    return raw, token_hash, expires_at


def hash_refresh(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()
