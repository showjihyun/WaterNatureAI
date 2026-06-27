# -*- coding: utf-8 -*-
"""데모: 뉴비즈솔루션 구독 활성화(실 서비스 경로, provider만 스텁).

start_subscription을 호출해 subscriptions(active)+billing_keys(암호화)+payments(done)
실 DB 행을 생성한다. 실제 Toss 빌링키 발급은 사업자 가맹 테스트키 필요 → provider 스텁.
"""
from __future__ import annotations

import io
import sys
import uuid

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import sqlalchemy as sa

from app.db.base import SessionLocal
from app.services.billing import service
from app.services.billing.provider import ChargeResult, PaymentProvider


class _StubToss(PaymentProvider):
    def issue_billing_key(self, customer_key: str, auth_key: str) -> str:
        return "bk_demo_seed_abc123"

    def charge(self, billing_key, amount, order_id, order_name, customer_key) -> ChargeResult:
        return ChargeResult(payment_key="pay_demo_seed_1", status="DONE")

    def handle_webhook(self, payload: dict) -> dict:
        return {}


db = SessionLocal()
cid = db.scalar(sa.text(
    "SELECT c.id FROM companies c JOIN users u ON u.company_id=c.id "
    "WHERE u.email='newbiz-5567@bizradar.ai'"
))
print("company:", cid)
sub = service.start_subscription(
    uuid.UUID(str(cid)), "demo_auth_key", f"cust_{cid}", db, provider=_StubToss()
)
print("subscription status:", sub.status)
print("current_period_end:", sub.current_period_end)

# 암호화 저장 확인
bk = db.execute(sa.text(
    "SELECT billing_key FROM billing_keys WHERE company_id=:c ORDER BY issued_at DESC LIMIT 1"
), {"c": str(cid)}).scalar()
print("billing_key at-rest (암호화):", (bk or "")[:32], "...")
pay = db.execute(sa.text(
    "SELECT status, amount FROM payments WHERE company_id=:c ORDER BY created_at DESC LIMIT 1"
), {"c": str(cid)}).fetchone()
print("payment:", pay.status, pay.amount)
db.close()
