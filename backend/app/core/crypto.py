"""대칭 암호화(at-rest) — LLM API 키 등 DB 저장 시크릿용.

Fernet(AES-128-CBC + HMAC, 인증 암호화). 마스터 키 = settings.app_secret_key
(미설정 시 jwt_secret 파생). **단방향 해시가 아니라 가역 암호화** — 저장한 키로
실제 LLM을 호출하려면 복호화가 필요하기 때문(해시는 복원 불가→사용 불가).
DB에는 평문이 아닌 ciphertext만 저장하고, API는 키 원문을 절대 반환하지 않는다.
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    master = settings.app_secret_key or settings.jwt_secret or "change-me"
    # 마스터 시크릿 → 32바이트 → urlsafe base64(Fernet 키 포맷)
    key = base64.urlsafe_b64encode(hashlib.sha256(master.encode()).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """평문 → ciphertext(문자열). DB 저장용."""
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str | None:
    """ciphertext → 평문. 마스터 키 불일치/손상 시 None."""
    try:
        return _fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, ValueError, TypeError):
        return None
