"""단위 테스트: app.core.crypto (대칭 암호화, 키 불필요)."""
from __future__ import annotations

from app.core import crypto


def test_encrypt_decrypt_roundtrip():
    secret = "sk-proj-abc123_XYZ-secret"
    ct = crypto.encrypt(secret)
    # ciphertext는 평문이 아니고 평문을 포함하지 않는다
    assert ct != secret
    assert secret not in ct
    # 복호화하면 원문 복원
    assert crypto.decrypt(ct) == secret


def test_encrypt_is_nondeterministic():
    """Fernet은 IV 포함 — 같은 평문도 매번 다른 ciphertext."""
    s = "same-secret"
    assert crypto.encrypt(s) != crypto.encrypt(s)


def test_decrypt_garbage_returns_none():
    assert crypto.decrypt("not-a-valid-token") is None
    assert crypto.decrypt("") is None
