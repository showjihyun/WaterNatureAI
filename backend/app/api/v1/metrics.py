"""플랫폼 집계(North Star) 지표 — 운영자 전용. 퍼널(추천→열람→저장→참여) + 비즈니스 KPI.

목표: 클릭 40% / 저장 20% / 참여 10%, 유료 30社, MRR ₩3M. (settings.admin_emails 게이트)
"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, select

from app.api.deps import CurrentAdmin, DbSession
from app.db.models.accounts import Company
from app.db.models.billing import Plan, Subscription
from app.db.models.opportunity import Match, Opportunity, UserOpportunityAction

router = APIRouter()

_TARGETS = {"open": 0.40, "save": 0.20, "participate": 0.10}
_PAYING_TARGET = 30
_MRR_TARGET = 3_000_000
_ACTIVE_SUB = ("active", "trialing")


class FunnelOut(BaseModel):
    total_companies: int
    ready_companies: int
    paying_companies: int
    paying_target: int
    mrr: int
    mrr_target: int
    recommended: int
    opened: int
    saved: int
    participated: int
    rates: dict     # {"open","save","participate"} — 추천 대비
    targets: dict   # {"open":0.4,"save":0.2,"participate":0.1}


@router.get("/funnel", response_model=FunnelOut)
def funnel(admin: CurrentAdmin, db: DbSession) -> FunnelOut:
    total_companies = db.scalar(select(func.count()).select_from(Company)) or 0
    ready_companies = (
        db.scalar(
            select(func.count()).select_from(Company).where(
                Company.onboarding_status == "ready"
            )
        )
        or 0
    )
    paying_companies = (
        db.scalar(
            select(func.count()).select_from(Subscription).where(
                Subscription.status.in_(_ACTIVE_SUB)
            )
        )
        or 0
    )
    mrr = (
        db.scalar(
            select(func.coalesce(func.sum(Plan.amount), 0))
            .select_from(Subscription)
            .join(Plan, Subscription.plan_code == Plan.code)
            .where(Subscription.status.in_(_ACTIVE_SUB))
        )
        or 0
    )

    # 추천(matches, canonical·open) — 플랫폼 전체. 퍼널 분모.
    recommended = (
        db.scalar(
            select(func.count())
            .select_from(Match)
            .join(Opportunity, Match.opportunity_id == Opportunity.id)
            .where(Opportunity.is_canonical.is_(True), Opportunity.status == "open")
        )
        or 0
    )
    # distinct (company, opportunity) 쌍으로 집계 — 분모(recommended=matches)와 동일 단위.
    # 열람은 engagement(opened|saved|participated|reviewed) 쌍 distinct로 계산해 단조성 보장
    # (저장·참여 쌍은 engagement의 부분집합 → 항상 열람 ≥ 관심 ≥ 참여).
    pair = func.count(
        func.distinct(
            func.concat(
                UserOpportunityAction.company_id,
                "|",
                UserOpportunityAction.opportunity_id,
            )
        )
    )
    counts = {
        row[0]: row[1]
        for row in db.execute(
            select(UserOpportunityAction.action_type, pair).group_by(
                UserOpportunityAction.action_type
            )
        ).all()
    }
    opened = (
        db.scalar(
            select(pair).where(
                UserOpportunityAction.action_type.in_(
                    ("opened", "saved", "participated", "reviewed")
                )
            )
        )
        or 0
    )
    saved = counts.get("saved", 0)
    participated = counts.get("participated", 0)
    base = recommended or 1

    return FunnelOut(
        total_companies=total_companies,
        ready_companies=ready_companies,
        paying_companies=paying_companies,
        paying_target=_PAYING_TARGET,
        mrr=int(mrr),
        mrr_target=_MRR_TARGET,
        recommended=recommended,
        opened=opened,
        saved=saved,
        participated=participated,
        rates={
            "open": round(opened / base, 4),
            "save": round(saved / base, 4),
            "participate": round(participated / base, 4),
        },
        targets=_TARGETS,
    )
