"""단위 테스트: embedding provider (fastembed 모킹 — 키 불필요, 실 다운로드 금지).

fastembed.TextEmbedding을 monkeypatch로 교체해 BgeProvider 동작을 검증.
(a) embed/embed_batch가 fastembed 호출 후 1024 list 반환.
(b) 차원 불일치 시 RuntimeError.
(c) get_provider()가 BgeProvider 반환.
실 네트워크/모델 다운로드 없음.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.embedding import provider as prov
from app.services.embedding.provider import (
    BgeProvider,
    get_provider,
)


@pytest.fixture(autouse=True)
def _clear_bge_cache():
    """_bge_model lru_cache 초기화 (테스트 간 격리)."""
    prov._bge_model.cache_clear()
    yield
    prov._bge_model.cache_clear()


def _fake_fastembed_model(dim: int) -> MagicMock:
    """embed() 호출 시 dim 차원 벡터를 texts 수만큼 반환하는 가짜 TextEmbedding."""
    model = MagicMock()
    model.embed.side_effect = lambda texts: ([0.1] * dim for _ in texts)
    return model


class TestBgeProvider:
    def test_embed_batch_returns_correct_shape(self, monkeypatch):
        fake = _fake_fastembed_model(1024)
        monkeypatch.setattr(prov.settings, "embedding_model", "BAAI/bge-m3")
        monkeypatch.setattr(prov.settings, "embedding_dim", 1024)
        monkeypatch.setattr(prov, "_bge_model", lambda _name: fake)

        p = BgeProvider()
        out = p.embed_batch(["문서1", "문서2"])

        assert len(out) == 2
        assert len(out[0]) == 1024
        assert all(isinstance(x, float) for x in out[0][:5])

    def test_embed_delegates_to_batch(self, monkeypatch):
        fake = _fake_fastembed_model(1024)
        monkeypatch.setattr(prov.settings, "embedding_model", "BAAI/bge-m3")
        monkeypatch.setattr(prov.settings, "embedding_dim", 1024)
        monkeypatch.setattr(prov, "_bge_model", lambda _name: fake)

        p = BgeProvider()
        vec = p.embed("단일 문서")

        assert isinstance(vec, list)
        assert len(vec) == 1024

    def test_empty_texts_returns_empty(self, monkeypatch):
        monkeypatch.setattr(prov.settings, "embedding_model", "BAAI/bge-m3")
        monkeypatch.setattr(prov.settings, "embedding_dim", 1024)
        p = BgeProvider()
        assert p.embed_batch([]) == []

    def test_dimension_mismatch_raises(self, monkeypatch):
        """fastembed가 기대와 다른 차원 반환 시 RuntimeError(pgvector 컬럼 보호)."""
        fake = _fake_fastembed_model(256)  # 잘못된 차원
        monkeypatch.setattr(prov.settings, "embedding_model", "BAAI/bge-m3")
        monkeypatch.setattr(prov.settings, "embedding_dim", 1024)
        monkeypatch.setattr(prov, "_bge_model", lambda _name: fake)

        p = BgeProvider()
        with pytest.raises(RuntimeError, match="차원 불일치"):
            p.embed_batch(["x"])

    def test_fastembed_called_with_model_name(self, monkeypatch):
        """_bge_model이 settings.embedding_model 값으로 호출되는지 확인."""
        captured: list[str] = []
        fake = _fake_fastembed_model(1024)

        def _capture(name: str):
            captured.append(name)
            return fake

        monkeypatch.setattr(prov.settings, "embedding_model", "BAAI/bge-m3")
        monkeypatch.setattr(prov.settings, "embedding_dim", 1024)
        monkeypatch.setattr(prov, "_bge_model", _capture)

        BgeProvider().embed("테스트")
        assert captured == ["BAAI/bge-m3"]


class TestGetProvider:
    def test_default_is_bge(self, monkeypatch):
        monkeypatch.setattr(prov.settings, "embedding_provider", "bge")
        assert isinstance(get_provider(), BgeProvider)

    def test_unknown_falls_back_to_bge(self, monkeypatch):
        monkeypatch.setattr(prov.settings, "embedding_provider", "unknown")
        assert isinstance(get_provider(), BgeProvider)
