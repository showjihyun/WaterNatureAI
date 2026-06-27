"""시스템 전역 설정 (key→JSONB). 마이그레이션 0003.

per-company(NotificationSetting)와 달리 **시스템 단일** 런타임 설정 보관소.
예: key='llm' → {"provider": "anthropic", "model": "claude-opus-4-8"}.
제3자 API 키는 여기 저장하지 않는다(.env 전용) — UI는 공급자/모델만 선택.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
