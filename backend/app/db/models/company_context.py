"""Company Context — Company Brain 산출 기업 역량. 마이그레이션 0001·0004(벡터).

정본: docs/04-architecture/company-brain.md, embed-worker.md.
벡터는 pgvector(본 행 embedding 컬럼)에 직접 저장 — point id = company_contexts.id.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CHAR, DateTime, ForeignKey, Index, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base
from app.db.models.common import UUIDPk


class CompanyContext(UUIDPk, Base):
    __tablename__ = "company_contexts"
    __table_args__ = (
        # 재임베딩 대상 부분 인덱스 (db-schema §10). 마이그레이션 0001 과 정합.
        Index(
            "idx_cc_needs_embed", "id",
            postgresql_where=text("embedded_hash IS DISTINCT FROM content_hash"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    context_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # 벡터(pgvector) — opportunities와 대칭, point id = id 재사용
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))
    # 재임베딩 추적 (0004)
    content_hash: Mapped[str | None] = mapped_column(CHAR(64))
    embedded_hash: Mapped[str | None] = mapped_column(CHAR(64))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding_version: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
