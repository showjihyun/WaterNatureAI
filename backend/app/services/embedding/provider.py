"""임베딩 제공자 추상화. 정본: embed-worker.md §2, blocker-resolution.md §2.

기본 BAAI/bge-m3 (fastembed, 무료 OSS, 키 불필요). 차원 1024.
모델·차원은 settings로 추상화(EMBEDDING_MODEL/EMBEDDING_DIM/EMBEDDING_PROVIDER).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from functools import lru_cache

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]: ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]: ...


class BgeProvider(EmbeddingProvider):
    """로컬 BGE-M3 (fastembed, 키 불필요).

    - 모델: settings.embedding_model (기본 'BAAI/bge-m3').
    - 차원: dense 벡터 1024 — pgvector vector(1024) 컬럼과 일치, 마이그레이션 불필요.
    - 최초 호출 시 모델 자동 다운로드(런타임 1회). 이후 캐시 재사용.
    - fastembed import는 lazy(함수 내부) — 미설치 환경에서 import-time 오류 없음.
    """

    def __init__(self) -> None:
        self.model_name = settings.embedding_model
        self.dim = settings.embedding_dim

    def _model(self):
        return _bge_model(self.model_name)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        model = self._model()
        vectors: list[list[float]] = [list(map(float, vec)) for vec in model.embed(texts)]
        if vectors and len(vectors[0]) != self.dim:
            raise RuntimeError(
                f"임베딩 차원 불일치: got {len(vectors[0])}, expected {self.dim} "
                f"(model={self.model_name})"
            )
        return vectors

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]


@lru_cache(maxsize=4)
def _bge_model(model_name: str):
    """fastembed.TextEmbedding 재사용(모델명별 캐시). SDK는 호출 시점에만 import(미설치 환경 보호)."""
    from fastembed import TextEmbedding  # noqa: PLC0415

    return TextEmbedding(model_name)


def get_provider() -> EmbeddingProvider:
    return {"bge": BgeProvider}.get(
        settings.embedding_provider, BgeProvider
    )()
