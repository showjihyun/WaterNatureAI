"""구독/결제 서비스 — 빌링키 발급·저장, 구독 생성/갱신, 정기결제. billing.md §3·§4·§6.

🚧 test 모드: SOLAPI/Toss 키 없으면 provider가 RuntimeError. 실호출은 전부 모킹/사업자 후.
⚠️ 빌링키는 at-rest 암호화 저장(crypto.Fernet) — DB에 평문 미저장, 로그 금지.
"""
from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import settings
from app.db.models.billing import BillingKey, Payment, Plan, Subscription
from app.services.billing.provider import (
    PaymentProvider,
    TossProvider,
    active_subscribed,
)

logger = logging.getLogger(__name__)

__all__ = [
    "start_subscription",
    "charge_due",
    "cancel_subscription",
    "apply_webhook_event",
    "active_subscribed",
    "is_company_subscribed",
]

# Toss 결제 상태 → 내부 payments.status 매핑(웹훅/조회 공통).
_TOSS_STATUS_MAP = {
    "DONE": "done",
    "CANCELED": "canceled",
    "PARTIAL_CANCELED": "canceled",
    "ABORTED": "failed",
    "EXPIRED": "failed",
    "WAITING_FOR_DEPOSIT": "ready",
}


def _plan(db: Session, plan_code: str) -> Plan:
    plan = db.get(Plan, plan_code)
    if plan is None:
        raise RuntimeError(f"플랜 없음: {plan_code} (plans 시드 확인)")
    return plan


def _add_month(dt: datetime) -> datetime:
    """+1개월(월말 보정 단순화: 30일 가산). 정밀 청구주기는 dunning 정비 시 개선."""
    return dt + timedelta(days=30)


def _order_id() -> str:
    """결제 멱등 키(우리 생성, UNIQUE) — **예측 불가 랜덤**.

    이전엔 sub_{company_id}_{timestamp}라 공격자가 자신의 company_id와 호출 시각으로
    유추해 웹훅을 위조(무료 구독)할 수 있었다. 192비트 랜덤으로 추측 불가하게 만든다.
    """
    return f"sub_{secrets.token_urlsafe(24)}"


def start_subscription(
    company_id: uuid.UUID,
    auth_key: str,
    customer_key: str,
    db: Session,
    *,
    provider: PaymentProvider | None = None,
) -> Subscription:
    """구독 시작: 빌링키 발급·저장 → subscription(active) → 첫 결제(payments).

    멱등 단순화: 회사당 1구독(uq_sub_company). 기존 구독 있으면 재사용/갱신.
    """
    prov = provider if provider is not None else TossProvider()
    plan_code = settings.billing_plan_default
    plan = _plan(db, plan_code)

    # ① 빌링키 발급(Toss) → billing_keys 저장. at-rest 암호화(아래 crypto.encrypt) — 로그 금지.
    billing_key_value = prov.issue_billing_key(customer_key, auth_key)
    bk = BillingKey(
        id=uuid.uuid4(),
        company_id=company_id,
        provider=settings.payment_provider,
        billing_key=crypto.encrypt(billing_key_value),  # at-rest 암호화(평문 미저장).
        customer_key=customer_key,
        status="active",
    )
    db.add(bk)
    db.flush()

    now = datetime.now(timezone.utc)
    period_end = _add_month(now)

    # ② subscription 생성/갱신(active, +1개월).
    sub = db.scalar(select(Subscription).where(Subscription.company_id == company_id))
    if sub is None:
        sub = Subscription(
            id=uuid.uuid4(),
            company_id=company_id,
            plan_code=plan_code,
            status="active",
            billing_key_id=bk.id,
            current_period_start=now,
            current_period_end=period_end,
        )
        db.add(sub)
    else:
        sub.plan_code = plan_code
        sub.status = "active"
        sub.billing_key_id = bk.id
        sub.current_period_start = now
        sub.current_period_end = period_end
        sub.canceled_at = None
    db.flush()

    # ③ 첫 결제(charge) → payments 기록.
    order_id = _order_id()
    order_name = f"{plan.name} 구독"
    pay = Payment(
        id=uuid.uuid4(),
        company_id=company_id,
        subscription_id=sub.id,
        order_id=order_id,
        amount=plan.amount,
        currency="KRW",
        status="ready",
        provider=settings.payment_provider,
    )
    db.add(pay)
    db.flush()

    try:
        res = prov.charge(
            billing_key_value, plan.amount, order_id, order_name, customer_key
        )
        # 명시적 DONE만 성공으로 인정. 빈/미상 상태를 done으로 강등 처리하지 않음(무결성).
        pay.status = "done" if res.status.upper() == "DONE" else (res.status.lower() or "failed")
        pay.provider_payment_key = res.payment_key or None
        pay.paid_at = datetime.now(timezone.utc)
    except Exception as exc:  # noqa: BLE001
        pay.status = "failed"
        pay.failure_reason = str(exc)
        sub.status = "past_due"
        logger.warning("start_subscription 첫 결제 실패 company=%s: %s", company_id, exc)

    db.commit()
    return sub


def charge_due(
    db: Session, *, provider: PaymentProvider | None = None, now: datetime | None = None
) -> dict:
    """정기 청구: period_end 경과한 active 구독을 charge → 갱신 / 실패 시 past_due.

    Returns: {"charged": n, "failed": n}.
    """
    prov = provider if provider is not None else TossProvider()
    _now = now or datetime.now(timezone.utc)
    charged = 0
    failed = 0

    subs = db.scalars(
        select(Subscription).where(
            Subscription.status == "active",
            Subscription.current_period_end.is_not(None),
            Subscription.current_period_end < _now,
        )
    ).all()

    for sub in subs:
        bk = db.get(BillingKey, sub.billing_key_id) if sub.billing_key_id else None
        if bk is None or bk.status != "active":
            sub.status = "past_due"
            failed += 1
            continue

        billing_key_plain = crypto.decrypt(bk.billing_key)
        if not billing_key_plain:
            # 복호화 실패(마스터키 불일치/손상) → 청구 불가, past_due.
            sub.status = "past_due"
            failed += 1
            logger.warning("charge_due: 빌링키 복호화 실패 company=%s", sub.company_id)
            continue

        plan = _plan(db, sub.plan_code)
        period_start = _now
        order_id = _order_id()
        pay = Payment(
            id=uuid.uuid4(),
            company_id=sub.company_id,
            subscription_id=sub.id,
            order_id=order_id,
            amount=plan.amount,
            currency="KRW",
            status="ready",
            provider=settings.payment_provider,
        )
        db.add(pay)
        db.flush()

        try:
            res = prov.charge(
                billing_key_plain, plan.amount, order_id, f"{plan.name} 구독", bk.customer_key
            )
            # 명시적 DONE만 성공으로 인정. 빈/미상 상태를 done으로 강등 처리하지 않음(무결성).
            pay.status = "done" if res.status.upper() == "DONE" else (res.status.lower() or "failed")
            pay.provider_payment_key = res.payment_key or None
            pay.paid_at = datetime.now(timezone.utc)
            sub.current_period_start = period_start
            sub.current_period_end = _add_month(period_start)
            charged += 1
        except Exception as exc:  # noqa: BLE001
            pay.status = "failed"
            pay.failure_reason = str(exc)
            sub.status = "past_due"  # TODO(dunning): 1·3·5일 재시도 후 canceled.
            failed += 1
            logger.warning("charge_due 결제 실패 company=%s: %s", sub.company_id, exc)

    db.commit()
    logger.info("charge_due: charged=%d failed=%d", charged, failed)
    return {"charged": charged, "failed": failed}


def cancel_subscription(db: Session, company_id: uuid.UUID) -> Subscription | None:
    """구독 해지 — 즉시 canceled(이후 정기결제 대상 제외, 게이트 False).

    period-end까지 접근 유지가 필요하면 후속에서 canceled_at + 만료 스윕으로 개선.
    """
    sub = db.scalar(select(Subscription).where(Subscription.company_id == company_id))
    if sub is None:
        return None
    sub.status = "canceled"
    sub.canceled_at = datetime.now(timezone.utc)
    db.commit()
    logger.info("cancel_subscription: company=%s", company_id)
    return sub


def apply_webhook_event(db: Session, event: dict) -> dict:
    """Toss 웹훅 이벤트 → payments/subscriptions 멱등 갱신.

    order_id(우리 멱등 키)로 payment를 찾아 상태가 바뀐 경우에만 갱신. 동일 이벤트
    재수신 시 no-op(updated=False). ⚠️ 서명 검증은 라우터에서 선행(웹훅 시크릿=사업자 후).
    """
    order_id = event.get("order_id")
    if not order_id:
        return {"ok": False, "reason": "no_order_id"}

    pay = db.scalar(select(Payment).where(Payment.order_id == order_id))
    if pay is None:
        return {"ok": False, "reason": "unknown_order", "order_id": order_id}

    new_status = _TOSS_STATUS_MAP.get(str(event.get("status") or "").upper())
    if not new_status or pay.status == new_status:
        return {"ok": True, "order_id": order_id, "status": pay.status, "updated": False}

    # 단방향 상태머신: 종료(canceled)된 결제를 done/ready로 되살리는 리플레이 차단.
    if pay.status == "canceled" and new_status != "canceled":
        logger.warning(
            "webhook replay blocked: canceled→%s order=%s", new_status, order_id
        )
        return {
            "ok": True, "order_id": order_id, "status": pay.status,
            "updated": False, "reason": "terminal_state",
        }

    pay.status = new_status
    if event.get("payment_key"):
        pay.provider_payment_key = event["payment_key"]
    if new_status == "done" and pay.paid_at is None:
        pay.paid_at = datetime.now(timezone.utc)

    # 구독 상태 동기화(결제 성공=active, 실패=past_due, 취소=canceled).
    if pay.subscription_id:
        sub = db.get(Subscription, pay.subscription_id)
        if sub is not None:
            if new_status == "done":
                sub.status = "active"
            elif new_status == "failed":
                sub.status = "past_due"
            elif new_status == "canceled":
                sub.status = "canceled"
                sub.canceled_at = datetime.now(timezone.utc)

    db.commit()
    logger.info("apply_webhook_event: order=%s status=%s", order_id, new_status)
    return {"ok": True, "order_id": order_id, "status": new_status, "updated": True}


def is_company_subscribed(db: Session, company_id: uuid.UUID) -> bool:
    """회사 구독 게이트: subscriptions.status IN ('active','trialing')."""
    status = db.scalar(
        select(Subscription.status).where(Subscription.company_id == company_id)
    )
    return active_subscribed(status)
