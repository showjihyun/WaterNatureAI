"""벡터 저장/검색 — PostgreSQL pgvector (별도 벡터 DB 없음).

정본: embed-worker.md §4 (point id = DB PK 재사용), db-schema §10.
벡터는 opportunities.embedding / company_contexts.embedding 컬럼에 직접 저장.
검색은 코사인 거리(<=>) ORDER BY. 컬렉션 개념 없음(테이블이 곧 컬렉션).
"""
from __future__ import annotations

import uuid
from typing import Any, cast

from sqlalchemy import select, update
from sqlalchemy.orm import DeclarativeBase, Session

from app.db.models.company_context import CompanyContext
from app.db.models.opportunity import Opportunity

# 임베딩 보유 모델(id + embedding 컬럼) — 과거 Qdrant 컬렉션명 호환 상수.
# 타입은 SQLAlchemy 모델 베이스로 두고, embedding 컬럼 접근은 cast로 명시.
EmbeddableModel = type[DeclarativeBase]
OPPORTUNITIES: EmbeddableModel = Opportunity
COMPANY_CONTEXTS: EmbeddableModel = CompanyContext


def store_embedding(
    db: Session, model: EmbeddableModel, point_id: str, vector: list[float]
) -> None:
    """해당 행의 embedding 컬럼에 벡터 저장(UPDATE). point_id = 행 PK(uuid)."""
    db.execute(
        update(model)
        .where(model.id == uuid.UUID(point_id))  # type: ignore[attr-defined]
        .values(embedding=vector)
    )


def get_embedding(
    db: Session, model: EmbeddableModel, point_id: str
) -> list[float] | None:
    """행 PK로 저장된 벡터 조회."""
    row = db.get(model, uuid.UUID(point_id))
    if row is None:
        return None
    embedding = cast("list[float] | None", getattr(row, "embedding", None))
    return list(embedding) if embedding is not None else None


def search_opportunities(
    db: Session,
    query_vector: list[float],
    limit: int = 50,
    status: str | None = "open",
    canonical_only: bool = False,
) -> list[tuple[str, float]]:
    """기업 벡터로 opportunities 코사인 유사도 top-N 검색 → (id, similarity) 리스트.

    similarity = 1.0 - cosine_distance (pgvector '<=>' 는 코사인 거리).
    거리 오름차순(= 유사도 내림차순) 정렬. NULL 임베딩 행은 제외.
    status 필터(기본 'open')는 SQL WHERE.
    canonical_only=True 면 dedup 대표(is_canonical)만 — 매칭이 중복본을 후보로 잡지 않게.
    """
    distance_col = Opportunity.embedding.cosine_distance(query_vector).label("distance")
    stmt = (
        select(Opportunity.id, distance_col)
        .where(Opportunity.embedding.isnot(None))
        .order_by(distance_col)
        .limit(limit)
    )
    if status is not None:
        stmt = stmt.where(Opportunity.status == status)
    if canonical_only:
        stmt = stmt.where(Opportunity.is_canonical.is_(True))
    return [(str(row[0]), 1.0 - float(row[1])) for row in db.execute(stmt).all()]


# ── payload 호환 메모 ──────────────────────────────────────────────────────
# Qdrant 시절 payload(source/category/status/deadline 등)는 별도 저장하지 않는다.
# 모두 opportunities 테이블 컬럼이라 검색 결과 id로 직접 조회/필터 가능.
def _payload_unused(*_a: Any, **_k: Any) -> None:  # noqa: D401 (의도적 no-op 문서)
    """pgvector에선 payload 미사용 — 행 컬럼이 곧 메타데이터."""
    return None
