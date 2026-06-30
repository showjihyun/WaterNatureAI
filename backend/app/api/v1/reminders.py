"""마감 리마인더 — 관심/진행 공고 중 마감 임박분(인앱 '마감 임박' 섹션).

GET /reminders : 회사 설정 윈도우(deadline_reminder_days, 기본 D-3) 내 마감 추적 공고, 임박순.
실 발송(카카오)은 Celery send_deadline_reminders + SOLAPI 게이트. 여기선 조회만.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import CurrentCompany, DbSession
from app.core.dates import KST
from app.db.models.accounts import Company, NotificationSetting
from app.db.models.opportunity import Opportunity
from app.schemas.opportunity import RecommendationItem
from app.services.feasibility.engine import assess_feasibility
from app.services.reminders import reminder_days_for, upcoming_reminders

router = APIRouter()


class ReminderItem(BaseModel):
    tracked_via: str  # "saved" | "pursuit"
    opportunity: RecommendationItem


def _d_day(deadline: datetime | None) -> int | None:
    if not deadline:
        return None
    return (deadline.astimezone(KST).date() - datetime.now(KST).date()).days


def _item(o: Opportunity, score: int | None, company: Company | None) -> RecommendationItem:
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
        opportunity_id=o.id, title=o.title, agency=o.agency, category=o.category, industry=o.industry,
        budget_amount=o.budget_amount, posted_at=o.posted_at, deadline=o.deadline,
        d_day=_d_day(o.deadline), score=score, reasons=[], saved=True,
        source=o.source, detail_url=o.detail_url, feasibility=feasibility,
    )


@router.get("", response_model=list[ReminderItem])
def list_reminders(company_id: CurrentCompany, db: DbSession) -> list[ReminderItem]:
    company = db.get(Company, company_id)
    cfg = db.get(NotificationSetting, company_id)
    days = reminder_days_for(cfg)
    rows = upcoming_reminders(db, company_id, days)
    return [
        ReminderItem(tracked_via=via, opportunity=_item(o, score, company))
        for o, score, via in rows
    ]
