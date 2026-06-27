"""단위 테스트: app.core.security — 비밀번호 해시 / JWT access token / refresh token.

정본: auth-onboarding.md §4·§7 / coding-testing.md §3.
외부 IO·DB 없음.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

import jwt
import pytest

from app.core.config import settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    hash_refresh,
    new_refresh_token,
    verify_password,
)


# ── 비밀번호 해시/검증 ───────────────────────────────────────────────────

class TestPasswordHash:
    def test_hash_is_not_plaintext(self):
        hashed = hash_password("mysecretpassword")
        assert hashed != "mysecretpassword"

    def test_verify_correct_password(self):
        raw = "correct-horse-battery-staple"
        hashed = hash_password(raw)
        assert verify_password(hashed, raw) is True

    def test_verify_wrong_password(self):
        hashed = hash_password("correct")
        assert verify_password(hashed, "wrong") is False

    def test_same_password_different_hash(self):
        """Argon2id salt → 같은 비밀번호라도 해시 다름."""
        h1 = hash_password("password123")
        h2 = hash_password("password123")
        assert h1 != h2

    def test_verify_correct_after_different_hashes(self):
        """salt가 달라도 원문 검증은 성공해야 함."""
        raw = "password123"
        h1 = hash_password(raw)
        h2 = hash_password(raw)
        assert verify_password(h1, raw) is True
        assert verify_password(h2, raw) is True

    def test_empty_password(self):
        """빈 문자열도 해시 가능."""
        hashed = hash_password("")
        assert verify_password(hashed, "") is True
        assert verify_password(hashed, "notempty") is False


# ── JWT access token ─────────────────────────────────────────────────────

class TestAccessToken:
    @pytest.fixture()
    def user_id(self) -> uuid.UUID:
        return uuid.uuid4()

    @pytest.fixture()
    def company_id(self) -> uuid.UUID:
        return uuid.uuid4()

    def test_create_and_decode(self, user_id, company_id):
        token = create_access_token(user_id=user_id, company_id=company_id, role="admin")
        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["company_id"] == str(company_id)
        assert payload["role"] == "admin"

    def test_type_claim_is_access(self, user_id, company_id):
        token = create_access_token(user_id=user_id, company_id=company_id, role="user")
        payload = decode_access_token(token)
        assert payload["type"] == "access"

    def test_company_id_in_payload(self, user_id, company_id):
        """company_id 클레임이 모든 조회를 격리하는 핵심."""
        token = create_access_token(user_id=user_id, company_id=company_id, role="user")
        payload = decode_access_token(token)
        assert "company_id" in payload
        assert payload["company_id"] == str(company_id)

    def test_exp_claim_present(self, user_id, company_id):
        token = create_access_token(user_id=user_id, company_id=company_id, role="user")
        payload = decode_access_token(token)
        assert "exp" in payload

    def test_expired_token_raises(self, user_id, company_id):
        """만료된 토큰 → jwt.ExpiredSignatureError."""
        # settings를 직접 패치하는 대신, 만료 시각을 과거로 직접 인코딩
        import time
        payload = {
            "sub": str(user_id),
            "company_id": str(company_id),
            "role": "user",
            "type": "access",
            "exp": int(time.time()) - 1,  # 이미 만료
        }
        token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_alg)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_invalid_signature_raises(self, user_id, company_id):
        token = create_access_token(user_id=user_id, company_id=company_id, role="user")
        # 서명 세그먼트 전체를 잘못된 값으로 교체(마지막 1자 변조는 base64 여유비트로
        # 동일 서명이 될 수 있어 비결정적 → 세그먼트 교체로 결정적 위변조).
        header_b64, payload_b64, _sig = token.split(".")
        tampered = f"{header_b64}.{payload_b64}.invalidsignature"
        with pytest.raises(jwt.InvalidSignatureError):
            decode_access_token(tampered)

    def test_different_users_different_tokens(self, company_id):
        uid1, uid2 = uuid.uuid4(), uuid.uuid4()
        t1 = create_access_token(user_id=uid1, company_id=company_id, role="user")
        t2 = create_access_token(user_id=uid2, company_id=company_id, role="user")
        assert t1 != t2


# ── refresh token ────────────────────────────────────────────────────────

class TestRefreshToken:
    def test_new_refresh_returns_three_values(self):
        raw, token_hash, expires_at = new_refresh_token()
        assert isinstance(raw, str)
        assert isinstance(token_hash, str)
        assert expires_at is not None

    def test_raw_and_hash_differ(self):
        raw, token_hash, _ = new_refresh_token()
        assert raw != token_hash

    def test_hash_is_sha256_hex_64(self):
        _, token_hash, _ = new_refresh_token()
        assert len(token_hash) == 64

    def test_hash_refresh_consistency(self):
        """hash_refresh(raw) == token_hash."""
        raw, token_hash, _ = new_refresh_token()
        assert hash_refresh(raw) == token_hash

    def test_different_refresh_tokens_unique(self):
        raw1, _, _ = new_refresh_token()
        raw2, _, _ = new_refresh_token()
        assert raw1 != raw2

    def test_different_hash_for_different_raws(self):
        raw1, h1, _ = new_refresh_token()
        raw2, h2, _ = new_refresh_token()
        assert h1 != h2

    def test_expires_at_is_future(self):
        from datetime import datetime, timezone
        _, _, expires_at = new_refresh_token()
        assert expires_at > datetime.now(timezone.utc)

    def test_expires_roughly_14_days(self):
        """만료 기간이 settings.jwt_refresh_ttl_days(14일) 기준."""
        from datetime import datetime, timezone
        _, _, expires_at = new_refresh_token()
        delta = expires_at - datetime.now(timezone.utc)
        # 13~15일 범위 (설정값 허용 오차)
        assert timedelta(days=13) < delta < timedelta(days=15 + 1)
