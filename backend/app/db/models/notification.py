"""발송/열람 추적 — notifications. 마이그레이션 0005.

정본: docs/04-architecture/daily-briefing.md §7.
멱등: (company_id, briefing_date) 유니크.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import UUIDPk


class Notification(UUIDPk, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        UniqueConstraint("company_id", "briefing_date", name="uq_notif_company_date"),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    briefing_date: Mapped[date] = mapped_column(Date, nullable=False)
    channel: Mapped[str] = mapped_column(String(16), nullable=False)  # alimtalk|friendtalk|sms
    template_code: Mapped[str | None] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)  # 렌더 변수 + match_ids
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # queued|sent|failed|fallback_sent
    provider: Mapped[str | None] = mapped_column(String(16))
    provider_msg_id: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
