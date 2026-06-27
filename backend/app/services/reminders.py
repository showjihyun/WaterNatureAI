"""마감 리마인더 — 관심(♥)·진행 관리 공고 중 마감 임박분 조회.

일일 디제스트(새 추천)와 분리된 채널: 이미 추적 중인 공고의 마감을 놓치지 않게.
GET /reminders(인앱 '마감 임박')와 Celery send_deadline_reminders(발송)가 공유.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select

from app.db.models.accounts import NotificationSetting
from app.db.models.opportunity import Match, Opportunity, Pursuit, UserOpportunityAction

DEFAULT_REMINDER_DAYS = 3  # cfg 미설정 시 D-3


def reminder_days_for(cfg: NotificationSetting | None) -> int:
    """리마인더 윈도우(일). null=기본 3, 0=끄기, N=D-N."""
    if cfg is None or cfg.deadline_reminder_days is None:
        return DEFAULT_REMINDER_DAYS
    return cfg.deadline_reminder_days


def upcoming_reminders(
    db, company_id: uuid.UUID, within_days: int
) -> list[tuple[Opportunity, int | None, str]]:
    """추적(관심 OR 진행 미완료) 공고 중 마감이 [지금, 지금+within_days] 인 것, 마감 임박순.

    Returns: (opportunity, match_score|None, tracked_via) 리스트. tracked_via ∈ {"saved","pursuit"}.
    한 공고가 관심·진행 둘 다면 'pursuit' 라벨 우선. within_days<=0 이면 빈 리스트(끄기).
    """
    if within_days <= 0:
        return []
    now = datetime.now(timezone.utc)
    until = now + timedelta(days=within_days)

    pursuit_ids = {
        oid for (oid,) in db.execute(
            select(Pursuit.opportunity_id).where(
                Pursuit.company_id == company_id, Pursuit.stage != "done"
            )
        ).all()
    }
    saved_ids = {
        oid for (oid,) in db.execute(
            select(UserOpportunityAction.opportunity_id).where(
                UserOpportunityAction.company_id == company_id,
                UserOpportunityAction.action_type == "saved",
            )
        ).all()
    }
    tracked: dict[uuid.UUID, str] = {oid: "saved" for oid in saved_ids}
    for oid in pursuit_ids:
        tracked[oid] = "pursuit"  # 진행이 관심보다 우선 라벨
    if not tracked:
        return []

    rows = db.execute(
        select(Opportunity, Match.score)
        .outerjoin(
            Match,
            and_(Match.opportunity_id == Opportunity.id, Match.company_id == company_id),
        )
        .where(
            Opportunity.id.in_(list(tracked.keys())),
            Opportunity.is_canonical.is_(True),
            Opportunity.status == "open",
            Opportunity.deadline.is_not(None),
            Opportunity.deadline >= now,
            Opportunity.deadline <= until,
        )
        .order_by(Opportunity.deadline.asc())
    ).all()
    return [(o, score, tracked[o.id]) for o, score in rows]
