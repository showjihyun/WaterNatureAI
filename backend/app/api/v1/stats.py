"""대시보드 통계(퍼널). MVP 성공기준(클릭40%/관심20%/참여10%) 매핑. dashboard-api §6."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from sqlalchemy import func, select

from app.api.deps import CurrentCompany, DbSession
from app.db.models.opportunity import Match, Opportunity, UserOpportunityAction
from app.schemas.opportunity import StatsOut

router = APIRouter()


@router.get("/stats", response_model=StatsOut)
def stats(
    company_id: CurrentCompany,
    db: DbSession,
    from_: datetime | None = None,
    to: datetime | None = None,
) -> StatsOut:
    # ── recommended: 추천(matches) 수 — 웹 퍼널 분모 ──────────────────────────
    # /recommendations/today 와 동일 필터(canonical·open), company 스코프, limit 없이 count.
    # Match.created_at 기준으로 from_/to 기간 필터 적용.
    rec_q = (
        select(func.count())
        .select_from(Match)
        .join(Opportunity, Match.opportunity_id == Opportunity.id)
        .where(
            Match.company_id == company_id,
            Opportunity.is_canonical.is_(True),
            Opportunity.status == "open",
        )
    )
    if from_:
        rec_q = rec_q.where(Match.created_at >= from_)
    if to:
        rec_q = rec_q.where(Match.created_at <= to)
    recommended: int = db.scalar(rec_q) or 0

    # ── opened/saved/participated: distinct 공고 수로 집계(퍼널 단조성 보장) ──────
    # 열람(opened)은 "engagement(opened|saved|participated|reviewed) 중 하나라도 있는
    # distinct 공고 수"로 계산 — 저장/참여만 한(열람 액션 미기록) 공고도 포함되어
    # 항상 열람 ≥ 관심 ≥ 참여 가 성립(저장·참여 공고는 engagement의 부분집합).
    act_q = select(
        UserOpportunityAction.action_type,
        func.count(func.distinct(UserOpportunityAction.opportunity_id)),
    ).where(UserOpportunityAction.company_id == company_id)
    if from_:
        act_q = act_q.where(UserOpportunityAction.created_at >= from_)
    if to:
        act_q = act_q.where(UserOpportunityAction.created_at <= to)
    counts: dict[str, int] = {
        row[0]: row[1]
        for row in db.execute(act_q.group_by(UserOpportunityAction.action_type)).all()
    }

    # 열람 = engagement 액션이 있는 distinct 공고 수(단일 쿼리 distinct count).
    eng_q = (
        select(func.count(func.distinct(UserOpportunityAction.opportunity_id)))
        .where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.action_type.in_(
                ("opened", "saved", "participated", "reviewed")
            ),
        )
    )
    if from_:
        eng_q = eng_q.where(UserOpportunityAction.created_at >= from_)
    if to:
        eng_q = eng_q.where(UserOpportunityAction.created_at <= to)

    opened = db.scalar(eng_q) or 0
    saved = counts.get("saved", 0)
    participated = counts.get("participated", 0)
    base = recommended or 1
    return StatsOut(
        recommended=recommended, opened=opened, saved=saved, participated=participated,
        rates={
            "open": round(opened / base, 4),
            "save": round(saved / base, 4),
            "participate": round(participated / base, 4),
        },
    )
