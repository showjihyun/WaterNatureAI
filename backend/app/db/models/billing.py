"""결제/구독 — plans/billing_keys/subscriptions/payments. 마이그레이션 0008.

정본: docs/04-architecture/billing.md (Toss, test 모드 — 사업자 확보 전 live 불가).
active_subscribed = subscriptions.status IN ('active','trialing').
"""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.common import UUIDPk


class Plan(Base):
    __tablename__ = "plans"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)  # basic_monthly
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # KRW (99000)
    interval: Mapped[str] = mapped_column(String(16), nullable=False, default="month")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class BillingKey(UUIDPk, Base):
    __tablename__ = "billing_keys"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="toss")
    billing_key: Mapped[str] = mapped_column(Text, nullable=False)  # 암호화 저장(카드정보 아님)
    customer_key: Mapped[str] = mapped_column(Text, nullable=False)
    card_company: Mapped[str | None] = mapped_column(String(32))
    card_last4: Mapped[str | None] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Subscription(UUIDPk, Base):
    __tablename__ = "subscriptions"
    __table_args__ = (UniqueConstraint("company_id", name="uq_sub_company"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    plan_code: Mapped[str] = mapped_column(String(32), ForeignKey("plans.code"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="trialing")
    billing_key_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("billing_keys.id")
    )
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Payment(UUIDPk, Base):
    __tablename__ = "payments"

    company_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("companies.id"), nullable=False
    )
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subscriptions.id")
    )
    order_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # 멱등 키
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="KRW")
    status: Mapped[str] = mapped_column(String(16), nullable=False)  # ready|done|failed|canceled
    provider: Mapped[str] = mapped_column(String(16), nullable=False, default="toss")
    provider_payment_key: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(Text)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
