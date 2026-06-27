"""공고 도메인 — sources/opportunities/changes/state/matches/actions/awards.

정본: docs/04-architecture/db-schema-opportunities.md (0002~0004, 0009).
키: (source, source_uid). 나라장터 source_uid=bidNtceNo, 차수는 source_ord.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db.base import Base
from app.db.models.common import UUIDPk

# 상태는 값이 고정 → Enum 유지 (source는 룩업 테이블 FK)
OpportunityStatus = Enum("open", "closed", "unknown", name="opportunity_status")

# action_type 표준 (dashboard-api §2, North Star 퍼널)
# deadline_reminded: 마감 리마인더 발송 멱등 키(meta={"deadline": iso}). 퍼널 집계엔 미포함.
ACTION_TYPES = (
    "notified", "opened", "reviewed", "saved", "participated", "hidden", "deadline_reminded",
)


class Source(Base):
    """소스 룩업 (ENUM 대신 — 소스 증설 시 INSERT 한 줄). 0003."""

    __tablename__ = "sources"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    tier: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    collector: Mapped[str | None] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Opportunity(UUIDPk, Base):
    __tablename__ = "opportunities"
    __table_args__ = (
        UniqueConstraint("source", "source_uid", name="uq_opportunities_source_uid"),
        # 부분 인덱스 (db-schema §3·§9). 마이그레이션 0001 과 정합 — autogenerate drift 방지.
        Index(
            "idx_opp_needs_embed", "id",
            postgresql_where=text("embedded_hash IS DISTINCT FROM content_hash"),
        ),
        Index(
            "idx_opp_open_deadline", "deadline",
            postgresql_where=text("status = 'open'"),
        ),
        Index("idx_opp_source_posted", "source", text("posted_at DESC")),
        # pgvector 코사인 ANN 인덱스(검색=vectorstore.search_opportunities).
        Index(
            "idx_opp_embedding_hnsw", "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    source: Mapped[str] = mapped_column(
        String(32), ForeignKey("sources.code"), nullable=False, index=True
    )
    source_uid: Mapped[str] = mapped_column(Text, nullable=False)
    source_ord: Mapped[int | None] = mapped_column(Integer)  # 나라장터 정정 차수
    detail_url: Mapped[str | None] = mapped_column(Text)

    title: Mapped[str] = mapped_column(Text, nullable=False)
    agency: Mapped[str | None] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)

    budget_raw: Mapped[str | None] = mapped_column(Text)
    budget_amount: Mapped[int | None] = mapped_column(BigInteger)

    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    application_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(OpportunityStatus, nullable=False, default="unknown")

    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    # 벡터(pgvector). point id 별도 없이 본 행에 직접 저장(db-schema §10: id 재사용).
    embedding: Mapped[list[float] | None] = mapped_column(Vector(settings.embedding_dim))
    embedded_hash: Mapped[str | None] = mapped_column(CHAR(64))
    embedded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    embedding_version: Mapped[str | None] = mapped_column(String(64))  # 0004

    # dedup (0004) — display-dedup.md
    dedup_group_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    is_canonical: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OpportunityChange(UUIDPk, Base):
    """변경 이력 (정정공고/내용변경)."""

    __tablename__ = "opportunity_changes"

    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    old_hash: Mapped[str | None] = mapped_column(CHAR(64))
    new_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    old_ord: Mapped[int | None] = mapped_column(Integer)
    new_ord: Mapped[int | None] = mapped_column(Integer)
    diff: Mapped[dict | None] = mapped_column(JSONB)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SourceIngestionState(Base):
    """소스별 증분 커서/모니터링."""

    __tablename__ = "source_ingestion_state"

    source: Mapped[str] = mapped_column(
        String(32), ForeignKey("sources.code"), primary_key=True
    )
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str | None] = mapped_column(String(20))  # running|success|failed
    collected_count: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Match(UUIDPk, Base):
    __tablename__ = "matches"
    __table_args__ = (
        UniqueConstraint("company_id", "opportunity_id", name="uq_matches_company_opp"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    subscore: Mapped[dict | None] = mapped_column(JSONB)  # 0004
    risk: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UserOpportunityAction(UUIDPk, Base):
    """퍼널 추적: notified/opened/reviewed/saved/participated (dashboard-api §2)."""

    __tablename__ = "user_opportunity_actions"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    action_type: Mapped[str] = mapped_column(String(20), nullable=False)  # ACTION_TYPES
    meta: Mapped[dict | None] = mapped_column(JSONB)  # 0007. hidden 사유 등 {"reason": ...}
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# 진행 관리 파이프라인 단계(순서). 0006.
PURSUIT_STAGES = ("reviewing", "preparing", "submitted", "done")


class Pursuit(UUIDPk, Base):
    """공고 진행 관리(파이프라인) — 회사가 추적 중인 공고와 현재 단계. (company, opp) 유니크.

    saved(관심)와 별개: '진행 추가'로 파이프라인에 올린 공고. submitted 도달 시 퍼널
    'participated' 액션을 기록(라우터에서) → 대시보드 참여 지표 반영.
    """

    __tablename__ = "pursuits"
    __table_args__ = (
        UniqueConstraint("company_id", "opportunity_id", name="uq_pursuit_company_opp"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("opportunities.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[str] = mapped_column(String(20), nullable=False, default="reviewing")
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OpportunityAward(UUIDPk, Base):
    """낙찰정보 — 나라장터 ScsbidInfoService (서비스2).

    opportunities 본 테이블과 별도 관리(추천 파이프라인 밖).
    bid_ntce_no+ord 로 소프트 링크(FK 없음 — 낙찰 수집 윈도우가 공고와 다를 수 있음).
    source_uid = f"{bidNtceNo}-{bidNtceOrd}-{bidClsfcNo}-{rbidNo}".
    """

    __tablename__ = "opportunity_awards"
    __table_args__ = (
        UniqueConstraint("source", "source_uid", name="uq_award_source_uid"),
        Index("ix_award_bid_ntce_no", "bid_ntce_no"),
    )

    source: Mapped[str] = mapped_column(
        String(32), ForeignKey("sources.code"), nullable=False, default="narajangter_scsbid"
    )
    source_uid: Mapped[str] = mapped_column(Text, nullable=False)

    # 공고 소프트 링크 (FK 없음)
    bid_ntce_no: Mapped[str | None] = mapped_column(Text)
    bid_ntce_ord: Mapped[int | None] = mapped_column(Integer)
    bid_clsfc_no: Mapped[str | None] = mapped_column(Text)   # 입찰분류번호
    rbid_no: Mapped[str | None] = mapped_column(Text)        # 재입찰번호

    category: Mapped[str | None] = mapped_column(Text)       # 물품/용역/공사/외자
    title: Mapped[str | None] = mapped_column(Text)          # bidNtceNm

    # 낙찰 업체
    winner_name: Mapped[str | None] = mapped_column(Text)    # bidwinnrNm
    winner_bizno: Mapped[str | None] = mapped_column(Text)   # bidwinnrBizno

    # 낙찰 금액·률·참가수
    award_amount: Mapped[int | None] = mapped_column(BigInteger)      # sucsfbidAmt
    award_rate: Mapped[Decimal | None] = mapped_column(Numeric(8, 4)) # sucsfbidRate
    participant_count: Mapped[int | None] = mapped_column(Integer)    # prtcptCnum

    # 기관·일시
    demand_agency: Mapped[str | None] = mapped_column(Text)           # dminsttNm
    real_opening_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # rlOpengDt
    final_award_date: Mapped[date | None] = mapped_column(Date)       # fnlSucsfDate
    registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))   # rgstDt

    # 해시·원본
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    raw_json: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # 수집 타임스탬프
    collected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
