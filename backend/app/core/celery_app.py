"""Celery 앱 + Beat 스케줄 (표준 일일 타임라인, KST).

정본: docs/00-overview/design-consistency-review.md §3.
수집을 KST 09:00로 이동(사용자 요청, settings.collect_schedule_hour/minute).
파이프라인 상대순서 보존: sweep(수집−10m) → 수집·임베딩 → dedup(+30m) →
매칭(+60m) → 브리핑(+120m). 기본값 09:00 기준 → 08:50/09:00/09:30/10:00/11:00.
celery timezone=Asia/Seoul 이므로 crontab 시각은 KST.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

celery_app = Celery(
    "bizradar",
    broker=settings.redis_url,
    # 결과 백엔드 미사용 — 파이프라인은 fire-and-forget(태스크 결과를 읽지 않음).
    # redis 결과 백엔드의 ResultConsumer가 쓰는 pubsub은 celery 5.6 ↔ redis-py 5.x에서
    # Connection.register_connect_callback 제거로 AsyncResult.__del__ 정리 시 AttributeError
    # 노이즈를 냄(실행엔 무해). 결과를 안 쓰므로 백엔드를 빼서 해당 경로 자체를 제거.
    include=[
        "app.services.collectors.tasks",
        "app.services.embedding.tasks",
        "app.services.dedup.tasks",
        "app.services.matching.tasks",
        "app.services.notifications.tasks",
        "app.services.billing.tasks",
    ],
)

celery_app.conf.update(timezone=settings.tz, enable_utc=False, task_ignore_result=True)


def _offset(base_hour: int, base_minute: int, delta_minutes: int) -> crontab:
    """수집 기준시각에서 delta(분)만큼 이동한 crontab 생성(일 경계 내 가정)."""
    base = datetime(2000, 1, 1, base_hour, base_minute)
    t = base + timedelta(minutes=delta_minutes)
    return crontab(hour=t.hour, minute=t.minute)


_H = settings.collect_schedule_hour      # 기본 9 (KST 09:00)
_M = settings.collect_schedule_minute     # 기본 0

celery_app.conf.beat_schedule = {
    "sweep-status": {  # 수집 직전(−10m): 마감 경과분 open→closed
        "task": "matching.sweep_opportunity_status",
        "schedule": _offset(_H, _M, -10),
    },
    "collect-daily": {  # KST 09:00 수집 (입찰공고 4유형 증분)
        "task": "collectors.run_all",
        "schedule": _offset(_H, _M, 0),
    },
    "dedup-daily": {
        "task": "dedup.run",
        "schedule": _offset(_H, _M, 30),
    },
    "match-daily": {
        "task": "matching.run_daily",
        "schedule": _offset(_H, _M, 60),
    },
    "briefing-daily": {
        "task": "notifications.send_daily_briefings",
        "schedule": _offset(_H, _M, 120),
    },
    "deadline-reminders-daily": {  # 브리핑 직후(+130m): 관심/진행 공고 마감 임박 리마인더
        "task": "notifications.send_deadline_reminders",
        "schedule": _offset(_H, _M, 130),
    },
    "collect-awards-daily": {  # KST 09:05 낙찰정보 수집 (ScsbidInfoService)
        "task": "collectors.run_scsbid",
        "schedule": _offset(_H, _M, 5),
    },
    "charge-due-daily": {  # KST 04:00 정기결제(청구 만기 구독 재청구) — 파이프라인과 분리
        "task": "billing.charge_due_subscriptions",
        "schedule": crontab(hour=4, minute=0),
    },
}
