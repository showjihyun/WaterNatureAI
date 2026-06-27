"""인앱 알림 — 마감 임박(관심/진행) + 최근 키워드 매칭 새 공고. 벨 아이콘 데이터.

GET /alerts : { deadline_reminders, keyword_hits }. 부수효과 없음(seen 상태는 클라이언트).
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import select

from app.api.deps import CurrentCompany, DbSession
from app.api.v1.reminders import ReminderItem
from app.db.models.accounts import Company, KeywordWatch, NotificationSetting
from app.db.models.opportunity import Opportunity
from app.schemas.opportunity import RecommendationItem
from app.services.feasibility.engine import assess_feasibility
from app.services.keyword_watch import keyword_match_rows
from app.services.reminders import reminder_days_for, upcoming_reminders

router = APIRouter()

_KEYWORD_RECENT_DAYS = 14  # 최근 수집된 키워드 매칭만 '새 공고'로
_KEYWORD_LIMIT = 15


class AlertsOut(BaseModel):
    deadline_reminders: list[ReminderItem]
    keyword_hits: list[RecommendationItem]


def _d_day(deadline: datetime | None) -> int | None:
    if not deadline:
        return None
    return (deadline.date() - datetime.now(timezone.utc).date()).days


def _item(
    o: Opportunity,
    score: int | None,
    company: Company | None,
    *,
    matched_keywords: list[str] | None = None,
    saved: bool = False,
) -> RecommendationItem:
    fr = assess_feasibility(
        tech_level=company.tech_level if company else None,
        max_project_budget=company.max_project_budget if company else None,
        capable_categories=company.capable_categories if company else None,
        budget_amount=o.budget_amount,
        category=o.category,
    )
    feasibility = (
        {"verdict": fr.verdict, "label": fr.label, "reasons": fr.reasons} if fr else None
    )
    return RecommendationItem(
        opportunity_id=o.id, title=o.title, agency=o.agency, category=o.category,
        budget_amount=o.budget_amount, posted_at=o.posted_at, deadline=o.deadline,
        d_day=_d_day(o.deadline), score=score, reasons=[], saved=saved,
        source=o.source, detail_url=o.detail_url, feasibility=feasibility,
        matched_keywords=matched_keywords or [],
    )


@router.get("", response_model=AlertsOut)
def list_alerts(company_id: CurrentCompany, db: DbSession) -> AlertsOut:
    company = db.get(Company, company_id)
    cfg = db.get(NotificationSetting, company_id)

    # 마감 임박(관심/진행)
    rem_rows = upcoming_reminders(db, company_id, reminder_days_for(cfg))
    reminders = [
        ReminderItem(tracked_via=via, opportunity=_item(o, score, company, saved=True))
        for o, score, via in rem_rows
    ]

    # 최근 키워드 매칭 새 공고
    keywords = [
        w.keyword
        for w in db.scalars(
            select(KeywordWatch).where(KeywordWatch.company_id == company_id)
        ).all()
    ]
    hit_rows = keyword_match_rows(
        db, company_id, keywords,
        limit=_KEYWORD_LIMIT, recent_days=_KEYWORD_RECENT_DAYS, order="created",
    )
    hits = [
        _item(o, score, company, matched_keywords=matched, saved=saved)
        for o, score, matched, saved in hit_rows
    ]
    return AlertsOut(deadline_reminders=reminders, keyword_hits=hits)
