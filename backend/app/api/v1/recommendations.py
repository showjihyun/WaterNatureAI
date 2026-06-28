"""오늘의 추천 (대시보드 Top 5). 카카오는 Top 3(daily-briefing). 정본: dashboard-api §4."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter
from sqlalchemy import and_, or_, select

from app.api.deps import CurrentCompany, DbSession
from app.core.dates import KST
from app.db.models.accounts import Company
from app.db.models.opportunity import Match, Opportunity, UserOpportunityAction
from app.schemas.opportunity import RecommendationItem
from app.services.feasibility.engine import FeasibilityResult, assess_feasibility

router = APIRouter()


def _d_day(deadline: datetime | None) -> int | None:
    if not deadline:
        return None
    return (deadline.astimezone(KST).date() - datetime.now(KST).date()).days


def _feasibility_dict(result: FeasibilityResult | None) -> dict | None:
    if result is None:
        return None
    return {"verdict": result.verdict, "label": result.label, "reasons": result.reasons}


def _split_reasons(reason: str | None) -> list[str]:
    """매칭 시 '; '로 합쳐 저장한 근거를 다시 개별 문장 리스트로(설명력)."""
    if not reason:
        return []
    return [r.strip() for r in reason.split(";") if r.strip()]


@router.get("/recommendations/today", response_model=list[RecommendationItem])
def today(company_id: CurrentCompany, db: DbSession) -> list[RecommendationItem]:
    company = db.get(Company, company_id)
    now = datetime.now(timezone.utc)
    # '관심없음(hidden)' 처리한 공고는 추천에서 제외(피드백 루프).
    hidden = (
        select(UserOpportunityAction.opportunity_id)
        .where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.action_type == "hidden",
        )
        .scalar_subquery()
    )
    rows = db.execute(
        select(Match, Opportunity)
        .join(Opportunity, Match.opportunity_id == Opportunity.id)
        .where(
            Match.company_id == company_id,
            Opportunity.is_canonical.is_(True),
            Opportunity.status == "open",
            # 마감 경과분 제외(sweep 지연 대비). 마감 미제공(NTIS 등)은 유지.
            or_(Opportunity.deadline.is_(None), Opportunity.deadline >= now),
            Opportunity.id.not_in(hidden),
        )
        .order_by(Match.score.desc())
        .limit(5)
    ).all()
    return [
        RecommendationItem(
            opportunity_id=o.id, title=o.title, agency=o.agency, category=o.category,
            budget_amount=o.budget_amount, posted_at=o.posted_at,
            deadline=o.deadline, d_day=_d_day(o.deadline),
            score=m.score, reasons=_split_reasons(m.reason), source=o.source,
            detail_url=o.detail_url,
            subscore=m.subscore, risk=(m.risk or None),
            feasibility=_feasibility_dict(
                assess_feasibility(
                    tech_level=company.tech_level if company else None,
                    max_project_budget=company.max_project_budget if company else None,
                    capable_categories=company.capable_categories if company else None,
                    budget_amount=o.budget_amount,
                    category=o.category,
                )
            ),
        )
        for m, o in rows
    ]


@router.get("/saved", response_model=list[RecommendationItem])
def saved(company_id: CurrentCompany, db: DbSession) -> list[RecommendationItem]:
    """관심 등록(♥)한 공고 목록. 최근 저장순. 매칭 점수 있으면 표시(없으면 None).

    마감 경과분도 포함(워치리스트) — 프론트가 'D-day/마감' 뱃지로 표시. 정렬은 클라이언트
    SortControl로 재정렬 가능.
    """
    company = db.get(Company, company_id)
    rows = db.execute(
        select(Opportunity, Match.score)
        .join(
            UserOpportunityAction,
            and_(
                UserOpportunityAction.opportunity_id == Opportunity.id,
                UserOpportunityAction.company_id == company_id,
                UserOpportunityAction.action_type == "saved",
            ),
        )
        .outerjoin(
            Match,
            and_(Match.opportunity_id == Opportunity.id, Match.company_id == company_id),
        )
        .where(Opportunity.is_canonical.is_(True))
        .order_by(UserOpportunityAction.created_at.desc())
        .limit(500)  # 동일 테넌트 메모리 증폭 방어(관심 목록 상한)
    ).all()
    return [
        RecommendationItem(
            opportunity_id=o.id, title=o.title, agency=o.agency, category=o.category,
            budget_amount=o.budget_amount, posted_at=o.posted_at,
            deadline=o.deadline, d_day=_d_day(o.deadline),
            score=score, reasons=[], saved=True, source=o.source,
            detail_url=o.detail_url,
            feasibility=_feasibility_dict(
                assess_feasibility(
                    tech_level=company.tech_level if company else None,
                    max_project_budget=company.max_project_budget if company else None,
                    capable_categories=company.capable_categories if company else None,
                    budget_amount=o.budget_amount,
                    category=o.category,
                )
            ),
        )
        for o, score in rows
    ]
