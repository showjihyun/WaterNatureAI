"""통합: billing service — start_subscription → subscriptions/payments, active_subscribed.

실 PG(alembic 스키마, plans 시드 0008) + Toss provider 모킹(외부 실호출 0).
TEST_DATABASE_URL 없으면 skip.
"""
from __future__ import annotations

import os
import uuid

import pytest

from app.services.billing.provider import ChargeResult, PaymentProvider

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — integration test skipped",
)


class _TxSession:
    """공유 트랜잭션 보존 래퍼: commit→flush (conftest rollback이 격리 담당)."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def commit(self):
        self._s.flush()


@pytest.fixture()
def tx(db_session):
    """service에 넘길 세션(commit→flush) + 검증 읽기 공용."""
    return _TxSession(db_session)


class _FakeToss(PaymentProvider):
    """외부 호출 없이 빌링키/charge 성공을 흉내내는 가짜 provider."""

    def __init__(self, *, fail_charge: bool = False) -> None:
        self.fail_charge = fail_charge
        self.issued: list[tuple[str, str]] = []
        self.charges: list[str] = []

    def issue_billing_key(self, customer_key: str, auth_key: str) -> str:
        self.issued.append((customer_key, auth_key))
        return "bk_fake_123"

    def charge(self, billing_key, amount, order_id, order_name, customer_key) -> ChargeResult:
        self.charges.append(order_id)
        if self.fail_charge:
            raise RuntimeError("card rejected")
        return ChargeResult(payment_key="pay_fake_1", status="DONE")

    def handle_webhook(self, payload: dict) -> dict:
        return {}


@pytest.fixture()
def company_id(db_session):
    from app.db.models.accounts import Company

    cid = uuid.uuid4()
    db_session.add(Company(id=cid, name="결제테스트기업", onboarding_status="ready"))
    db_session.flush()
    return cid


class TestStartSubscription:
    def test_creates_subscription_and_payment(self, tx, company_id):
        from sqlalchemy import select

        from app.db.models.billing import BillingKey, Payment
        from app.services.billing import service

        fake = _FakeToss()
        sub = service.start_subscription(
            company_id, "auth_1", "cust_1", tx, provider=fake
        )

        assert sub.status == "active"
        assert sub.plan_code == "basic_monthly"
        assert sub.current_period_end is not None
        assert fake.issued == [("cust_1", "auth_1")]

        # billing_keys 저장
        bk = tx.scalar(select(BillingKey).where(BillingKey.company_id == company_id))
        assert bk is not None
        assert bk.customer_key == "cust_1"

        # payments: 첫 결제 done
        pay = tx.scalar(select(Payment).where(Payment.company_id == company_id))
        assert pay is not None
        assert pay.status == "done"
        assert pay.amount == 99000
        assert pay.provider_payment_key == "pay_fake_1"

    def test_failed_charge_sets_past_due(self, tx, company_id):
        from sqlalchemy import select

        from app.db.models.billing import Payment
        from app.services.billing import service

        fake = _FakeToss(fail_charge=True)
        sub = service.start_subscription(
            company_id, "auth_1", "cust_1", tx, provider=fake
        )

        assert sub.status == "past_due"
        pay = tx.scalar(select(Payment).where(Payment.company_id == company_id))
        assert pay.status == "failed"
        assert pay.failure_reason is not None

    def test_idempotent_one_subscription_per_company(self, tx, company_id):
        from sqlalchemy import func, select

        from app.db.models.billing import Subscription
        from app.services.billing import service

        service.start_subscription(company_id, "a1", "c1", tx, provider=_FakeToss())
        service.start_subscription(company_id, "a2", "c2", tx, provider=_FakeToss())

        count = tx.scalar(
            select(func.count()).select_from(Subscription).where(
                Subscription.company_id == company_id
            )
        )
        assert count == 1


class TestIsCompanySubscribed:
    def test_active_after_start(self, tx, company_id):
        from app.services.billing import service

        service.start_subscription(company_id, "a1", "c1", tx, provider=_FakeToss())
        assert service.is_company_subscribed(tx, company_id) is True

    def test_no_subscription_false(self, tx, company_id):
        from app.services.billing import service

        assert service.is_company_subscribed(tx, company_id) is False


class TestChargeDue:
    def test_charges_expired_active(self, tx, company_id):
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.db.models.billing import Payment, Subscription
        from app.services.billing import service

        # 구독 시작 후 period_end 를 과거로 강제 → 만기 청구 대상.
        service.start_subscription(company_id, "a1", "c1", tx, provider=_FakeToss())
        sub = tx.scalar(
            select(Subscription).where(Subscription.company_id == company_id)
        )
        sub.current_period_end = datetime.now(timezone.utc) - timedelta(days=1)
        tx.flush()

        result = service.charge_due(tx, provider=_FakeToss())
        assert result["charged"] == 1

        # 결제 2건(첫 결제 + 정기) 생성, period_end 갱신(미래로).
        pays = tx.scalars(
            select(Payment).where(Payment.company_id == company_id)
        ).all()
        assert len(pays) == 2
        tx.refresh(sub)
        assert sub.status == "active"
        assert sub.current_period_end > datetime.now(timezone.utc)

    def test_failed_charge_sets_past_due(self, tx, company_id):
        from datetime import datetime, timedelta, timezone

        from sqlalchemy import select

        from app.db.models.billing import Subscription
        from app.services.billing import service

        service.start_subscription(company_id, "a1", "c1", tx, provider=_FakeToss())
        sub = tx.scalar(
            select(Subscription).where(Subscription.company_id == company_id)
        )
        sub.current_period_end = datetime.now(timezone.utc) - timedelta(days=1)
        tx.flush()

        result = service.charge_due(tx, provider=_FakeToss(fail_charge=True))
        assert result["failed"] == 1
        tx.refresh(sub)
        assert sub.status == "past_due"


class TestBillingKeyEncryption:
    def test_billing_key_stored_encrypted(self, tx, company_id):
        """billing_keys.billing_key는 평문 미저장 — ciphertext, 복호화 시 원문 일치."""
        from sqlalchemy import select

        from app.core import crypto
        from app.db.models.billing import BillingKey
        from app.services.billing import service

        service.start_subscription(company_id, "a1", "c1", tx, provider=_FakeToss())
        bk = tx.scalar(select(BillingKey).where(BillingKey.company_id == company_id))
        assert bk.billing_key != "bk_fake_123"  # 평문 미저장
        assert "bk_fake_123" not in bk.billing_key
        assert crypto.decrypt(bk.billing_key) == "bk_fake_123"  # 복호화 일치


class TestCancel:
    def test_cancel_sets_canceled_and_gate_false(self, tx, company_id):
        from app.services.billing import service

        service.start_subscription(company_id, "a1", "c1", tx, provider=_FakeToss())
        assert service.is_company_subscribed(tx, company_id) is True

        sub = service.cancel_subscription(tx, company_id)
        assert sub.status == "canceled"
        assert sub.canceled_at is not None
        assert service.is_company_subscribed(tx, company_id) is False

    def test_cancel_no_subscription_returns_none(self, tx, company_id):
        from app.services.billing import service

        assert service.cancel_subscription(tx, company_id) is None


class TestWebhookEvent:
    def test_webhook_idempotent_update(self, tx, company_id):
        from sqlalchemy import select

        from app.db.models.billing import Payment
        from app.services.billing import service

        service.start_subscription(company_id, "a1", "c1", tx, provider=_FakeToss())
        pay = tx.scalar(select(Payment).where(Payment.company_id == company_id))
        # 첫 결제는 done. 웹훅으로 CANCELED 수신 → canceled 갱신.
        event = {"order_id": pay.order_id, "status": "CANCELED", "payment_key": "pk"}
        r1 = service.apply_webhook_event(tx, event)
        assert r1["updated"] is True and r1["status"] == "canceled"
        # 동일 이벤트 재수신 → no-op(멱등).
        r2 = service.apply_webhook_event(tx, event)
        assert r2["updated"] is False

    def test_webhook_unknown_order(self, tx, company_id):
        from app.services.billing import service

        r = service.apply_webhook_event(tx, {"order_id": "nope", "status": "DONE"})
        assert r["ok"] is False and r["reason"] == "unknown_order"
