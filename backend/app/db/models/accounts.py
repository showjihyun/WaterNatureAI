"""계정/회사/수신설정/리프레시토큰. 마이그레이션 0001·0006·0007.

정본: docs/04-architecture/auth-onboarding.md, db-schema §11.
관계: users N:1 companies. 알림·매칭 단위 = company.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.common import TimestampMixin, UUIDPk


class Company(UUIDPk, TimestampMixin, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    region: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))  # 카카오 발송용 (0006)
    onboarding_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="profile"  # profile→document→brain→ready
    )

    # 수행 역량 (0002) — 수행 가능성 판단(feasibility engine)용
    tech_level: Mapped[int | None] = mapped_column(SmallInteger)           # 기술수준 1~5
    max_project_budget: Mapped[int | None] = mapped_column(BigInteger)     # 감당 가능 최대 예산(KRW)
    capable_categories: Mapped[list | None] = mapped_column(JSONB)         # 수행 유형(예: ["물품","용역"])

    # 온보딩 프로필 (0004) — Company Brain LLM 추출 입력
    services: Mapped[list | None] = mapped_column(JSONB)        # 주요 서비스/제품
    technologies: Mapped[list | None] = mapped_column(JSONB)    # 보유 기술 스택
    customers: Mapped[list | None] = mapped_column(JSONB)       # 주요 고객사 유형
    certifications: Mapped[list | None] = mapped_column(JSONB)  # 보유 인증

    # 회사소개서 파싱 (0005, FR-004) — 업로드 PDF에서 추출한 텍스트. Brain 입력 보강.
    document_text: Mapped[str | None] = mapped_column(Text)        # 추출 텍스트(캡 적용)
    document_filename: Mapped[str | None] = mapped_column(String(255))  # 원본 파일명(UI 표시)

    users: Mapped[list["User"]] = relationship(back_populates="company")
    notification_setting: Mapped["NotificationSetting | None"] = relationship(
        back_populates="company", uselist=False
    )


class User(UUIDPk, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id"), index=True
    )
    role: Mapped[str] = mapped_column(String(32), nullable=False, default="company_admin")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    company: Mapped["Company"] = relationship(back_populates="users")


class RefreshToken(UUIDPk, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)  # 원문 미저장
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class NotificationSetting(Base):
    __tablename__ = "notification_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="alimtalk")
    send_hour: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=8)  # KST
    send_empty: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # 맞춤 알림 규칙 (0008) — 브리핑 필터. null=기본(match_threshold·전체 소스).
    min_score: Mapped[int | None] = mapped_column(SmallInteger)        # 알림 적합도 임계값
    excluded_sources: Mapped[list | None] = mapped_column(JSONB)       # 브리핑 제외 소스 코드
    # 마감 리마인더 (0010) — 관심/진행 공고 마감 N일 전 알림. null=기본 3(D-3), 0=끄기.
    deadline_reminder_days: Mapped[int | None] = mapped_column(SmallInteger)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    company: Mapped["Company"] = relationship(back_populates="notification_setting")


class KeywordWatch(UUIDPk, Base):
    """키워드 워치(저장 검색) — 회사가 지정한 키워드. 공고 제목에 포함되면 워치 피드 대상. 0009.

    AI 매칭과 독립적인 도메인 지식 기반 보완 채널(매처가 낮게 본 공고도 키워드로 포착).
    (company, lower(keyword)) 유니크(대소문자 무시) — 함수 기반 유니크 인덱스.
    """

    __tablename__ = "keyword_watches"
    __table_args__ = (
        Index(
            "uq_keyword_watch_company_lower",
            "company_id",
            text("lower(keyword)"),
            unique=True,
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    keyword: Mapped[str] = mapped_column(String(80), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
