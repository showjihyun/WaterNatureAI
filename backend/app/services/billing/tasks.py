"""정기결제 Celery 태스크. 정본: docs/04-architecture/billing.md §4.

charge_due를 일 1회(beat) 실행 — current_period_end 경과한 active 구독을 재청구.
🚧 Toss 키 미설정/오류 시 provider가 RuntimeError → 해당 구독만 past_due로 기록(태스크는
   죽지 않음). 빌링키는 at-rest 암호화이므로 charge 직전 복호화(service.charge_due 내부).
"""
from __future__ import annotations

import logging

from app.core.celery_app import celery_app
from app.db.base import SessionLocal
from app.services.billing import service as billing_service

logger = logging.getLogger(__name__)


@celery_app.task(name="billing.charge_due_subscriptions")
def charge_due_subscriptions() -> dict:
    """청구 만기 도래 구독 정기결제. Returns {"charged": n, "failed": n}."""
    db = SessionLocal()
    try:
        result = billing_service.charge_due(db)
        logger.info("charge_due_subscriptions: %s", result)
        return result
    finally:
        db.close()
