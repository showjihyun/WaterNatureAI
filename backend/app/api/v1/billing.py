"""결제/구독 API. 정본: docs/04-architecture/billing.md §3·§6.

- GET  /billing/config       : Toss 클라이언트 키(publishable) + 플랜 정보(프론트 SDK·표시용).
- POST /billing/subscribe    : 빌링키 발급 → 구독 시작(첫 결제). CurrentCompany 스코프.
- GET  /billing/subscription : 현재 구독 상태(+플랜).
- POST /billing/cancel       : 구독 해지.
- POST /billing/webhook      : Toss 웹훅 수신 → payments/subscriptions 멱등 갱신.

🚧 test 모드: 키 미설정 시 provider RuntimeError → 502 매핑. 라이브는 사업자+가맹 후.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentCompany, DbSession
from app.core.config import settings
from app.db.models.billing import Plan, Subscription
from app.services.billing import service as billing_service
from app.services.billing.provider import TossProvider

logger = logging.getLogger(__name__)

router = APIRouter()


class SubscribeIn(BaseModel):
    auth_key: str
    customer_key: str


def _plan_dict(db: DbSession) -> dict:
    plan = db.get(Plan, settings.billing_plan_default)
    if plan is None:
        return {"code": settings.billing_plan_default, "name": "구독", "amount": 0, "interval": "month"}
    return {"code": plan.code, "name": plan.name, "amount": plan.amount, "interval": plan.interval}


@router.get("/config")
def billing_config(company_id: CurrentCompany, db: DbSession) -> dict:
    """프론트 결제 위젯 초기화용 — Toss 클라이언트 키(publishable) + 플랜.

    client_key는 공개 가능한 키(브라우저 노출 정상). secret_key는 절대 반환하지 않는다.
    """
    return {
        "provider": settings.payment_provider,
        "client_key": settings.toss_client_key,
        "mode": settings.toss_mode,
        # Toss customerKey(자동결제 빌링) — 회사당 안정 식별자. 카드정보 아님.
        "customer_key": f"cust_{company_id}",
        "plan": _plan_dict(db),
    }


@router.post("/subscribe")
def subscribe(body: SubscribeIn, company_id: CurrentCompany, db: DbSession) -> dict:
    """카드 인증(authKey)으로 빌링키 발급 → 구독 시작."""
    try:
        sub = billing_service.start_subscription(
            company_id, body.auth_key, body.customer_key, db
        )
    except RuntimeError as exc:
        # 키 미설정/Toss 오류 — test 모드에서 흔함.
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return _subscription_dict(sub, db)


@router.get("/subscription")
def get_subscription(company_id: CurrentCompany, db: DbSession) -> dict:
    """현재 구독 상태(없으면 status='none')."""
    sub = db.scalar(select(Subscription).where(Subscription.company_id == company_id))
    if sub is None:
        return {"status": "none", "plan_code": None, "current_period_end": None, "plan": _plan_dict(db)}
    return _subscription_dict(sub, db)


@router.post("/cancel")
def cancel(company_id: CurrentCompany, db: DbSession) -> dict:
    """현재 구독 해지(즉시 canceled)."""
    sub = billing_service.cancel_subscription(db, company_id)
    if sub is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "구독이 없습니다.")
    return _subscription_dict(sub, db)


def _subscription_dict(sub: Subscription, db: DbSession) -> dict:
    return {
        "status": sub.status,
        "plan_code": sub.plan_code,
        "current_period_end": (
            sub.current_period_end.isoformat() if sub.current_period_end else None
        ),
        "canceled_at": sub.canceled_at.isoformat() if sub.canceled_at else None,
        "plan": _plan_dict(db),
    }


# 공유 시크릿 HMAC 서명 헤더 후보(Toss 실연동 시 실제 서명 헤더명으로 정리).
_WEBHOOK_SIG_HEADERS = (
    "X-BizRadar-Signature",
    "TossPayments-Webhook-Signature",
    "X-Toss-Signature",
)


def _verify_webhook_signature(raw: bytes, signature: str | None) -> bool:
    """웹훅 진위 확인 — 공유 시크릿 HMAC-SHA256(raw body) 상수시간 비교.

    fail-closed: 시크릿 미설정 또는 서명 없음/불일치면 False → 호출 거부.
    이전엔 무인증이라 누구나 '결제완료'를 위조해 무료 구독을 활성화할 수 있었다.
    운영 전환 시 TOSS_WEBHOOK_SECRET을 주입하고 Toss 콘솔에서 동일 시크릿으로
    서명하도록 설정(또는 Toss 공식 서명 검증/결제 재조회 방식으로 교체)한다.
    """
    secret = settings.toss_webhook_secret
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


@router.post("/webhook")
async def webhook(request: Request, db: DbSession) -> dict:
    """Toss 웹훅 수신 → payments/subscriptions 멱등 갱신.

    보안: 공유 시크릿(HMAC-SHA256) 서명 검증을 **선행**한다(fail-closed). 검증을 통과한
    바로 그 바이트(raw)로만 JSON을 파싱한다.
    """
    raw = await request.body()
    signature = next(
        (request.headers[h] for h in _WEBHOOK_SIG_HEADERS if h in request.headers),
        None,
    )
    if not _verify_webhook_signature(raw, signature):
        logger.warning("toss webhook rejected: missing/invalid signature")
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "webhook signature verification failed"
        )
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid json body") from exc

    event = TossProvider().handle_webhook(payload)
    result = billing_service.apply_webhook_event(db, event)
    logger.info(
        "toss webhook: event=%s order=%s applied=%s",
        event.get("event_type"), event.get("order_id"), result.get("updated"),
    )
    return {"ok": True, **result}
