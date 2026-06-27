"""임베딩 provider 스모크 테스트 (BGE-M3, fastembed).

기본은 skip — 모델 다운로드가 무거우므로 환경변수 EMBED_SMOKE=1 있을 때만 실행.
있으면 실제 fastembed로 BAAI/bge-m3를 로드해 1024차원 벡터 생성 확인.

실행: EMBED_SMOKE=1 pytest tests/smoke/test_embedding_live.py -v
"""
from __future__ import annotations

import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("EMBED_SMOKE"),
    reason="EMBED_SMOKE not set — bge-m3 model download skipped (set EMBED_SMOKE=1 to run)",
)


def test_bge_embed_live() -> None:
    """실 fastembed 호출 → embedding_dim 차원 벡터 1건."""
    from app.core.config import settings
    from app.services.embedding.provider import BgeProvider

    vec = BgeProvider().embed("나라장터 사무용 PC 구매 입찰공고 — 서울시")
    assert isinstance(vec, list)
    assert len(vec) == settings.embedding_dim
    assert all(isinstance(x, float) for x in vec[:5])


def test_bge_embed_batch_live() -> None:
    """배치 임베딩 → 입력 수만큼 반환."""
    from app.core.config import settings
    from app.services.embedding.provider import BgeProvider

    out = BgeProvider().embed_batch(["공고 A 본문", "공고 B 본문"])
    assert len(out) == 2
    assert len(out[0]) == settings.embedding_dim
