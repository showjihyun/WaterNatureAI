"""추천 조회(FR-009)·상세. 정본: dashboard-api.md §4·§5."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, or_, select

from app.api.deps import CurrentCompany, DbSession
from app.core.dates import KST
from app.db.models.accounts import Company
from app.db.models.opportunity import Match, Opportunity, OpportunityAward
from app.schemas.opportunity import AwardItem, AwardList, OpportunityList, RecommendationItem
from app.services.feasibility.engine import FeasibilityResult, assess_feasibility

router = APIRouter()

_SIDO_PREFIX = {
    "서울": "서울", "부산": "부산", "대구": "대구", "인천": "인천", "광주": "광주",
    "대전": "대전", "울산": "울산", "세종": "세종", "경기": "경기", "강원": "강원",
    "충청북도": "충북", "충북": "충북", "충청남도": "충남", "충남": "충남",
    "전라북도": "전북", "전북": "전북", "전라남도": "전남", "전남": "전남",
    "경상북도": "경북", "경북": "경북", "경상남도": "경남", "경남": "경남",
    "제주": "제주", "전국": "전국",
}


def _normalize_sido(region: str | None) -> str | None:
    if not region:
        return None
    for prefix, sido in _SIDO_PREFIX.items():
        if region.startswith(prefix):
            return sido
    return None

_ALLOWED_SORT = {"score", "deadline", "posted", "budget", "feasibility"}
_ALLOWED_FEASIBILITY = {"go", "review", "no_go"}

# feasibility verdict 정렬 우선순위 (낮을수록 앞)
_VERDICT_RANK: dict[str | None, int] = {"go": 0, "review": 1, "no_go": 2, None: 3}


def _d_day(deadline: datetime | None) -> int | None:
    # 추천(recommendations.today)과 동일 계산 — 목록도 같은 d_day 노출(마감일 미정 방지).
    if not deadline:
        return None
    return (deadline.astimezone(KST).date() - datetime.now(KST).date()).days


def _feasibility_dict(result: FeasibilityResult | None) -> dict | None:
    if result is None:
        return None
    return {"verdict": result.verdict, "label": result.label, "reasons": result.reasons}


def _dedup_key(o: Opportunity) -> object:
    """표시 dedup 키. dedup_group_id(있으면) 우선, 없으면 내용 키(title/agency/budget).

    나라장터는 동일 공고를 서로 다른 source_uid(bidNtceNo)로 재게시 → source_uid/
    content_hash로는 안 잡힘. dedup.run(display-dedup) 미가동 상태에서 표시단 dedup.
    """
    if o.dedup_group_id is not None:
        return ("g", o.dedup_group_id)
    return ("c", o.title, o.agency, o.budget_amount)


def _build_item(m: Match, o: Opportunity, company: Company | None) -> RecommendationItem:
    return RecommendationItem(
        opportunity_id=o.id, title=o.title, agency=o.agency, category=o.category,
        budget_amount=o.budget_amount, posted_at=o.posted_at, deadline=o.deadline,
        d_day=_d_day(o.deadline),
        score=m.score, reasons=[m.reason] if m.reason else [], source=o.source,
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


@router.get("", response_model=OpportunityList)
def list_opportunities(
    company_id: CurrentCompany,
    db: DbSession,
    agency: str | None = None,
    budget_min: int | None = None,
    budget_max: int | None = None,
    deadline_before: datetime | None = None,
    min_score: int | None = None,
    source: list[str] | None = Query(None),  # 출처 필터(나라장터·kstartup·ntis·bizinfo)
    region: str | None = None,
    category: str | None = None,
    sort: str = Query("score"),
    feasibility: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> OpportunityList:
    # 미허용 sort 값은 score로 폴백; 미허용 feasibility 값은 None 취급(전체)
    effective_sort = sort if sort in _ALLOWED_SORT else "score"
    effective_feasibility = feasibility if feasibility in _ALLOWED_FEASIBILITY else None

    company = db.get(Company, company_id)
    now = datetime.now(timezone.utc)
    base = (
        select(Match, Opportunity)
        .join(Opportunity, Match.opportunity_id == Opportunity.id)
        .where(
            Match.company_id == company_id,
            Opportunity.is_canonical.is_(True),
            Opportunity.status == "open",
            # 방어: sweep 지연 대비 — 마감 지난 공고는 목록에서 제외(마감 미정=NTIS 등은 유지).
            or_(Opportunity.deadline.is_(None), Opportunity.deadline >= now),
        )
    )
    if agency:
        base = base.where(Opportunity.agency.ilike(f"%{agency}%"))
    if budget_min is not None:
        base = base.where(Opportunity.budget_amount >= budget_min)
    if budget_max is not None:
        base = base.where(Opportunity.budget_amount <= budget_max)
    if deadline_before is not None:
        base = base.where(Opportunity.deadline <= deadline_before)
    if min_score is not None:
        base = base.where(Match.score >= min_score)
    if source:
        base = base.where(Opportunity.source.in_(source))
    if category:
        base = base.where(Opportunity.category == category)

    # 단일 파이썬 경로: 표시단 dedup(동일 공고 중복 제거)이 필요해 전 행을 가져온 뒤
    # 적합도 최고 1건만 남기고 정렬·페이징. (company 스코프라 행 수가 작음 — 수십 건)
    rows = db.execute(base).all()
    if region == "전국":
        rows = [(m, o) for m, o in rows if _normalize_sido(o.region) == "전국"]
    elif region:
        # 특정 시도 선택 시 '전국'(전 지역 유효) 공고도 포함. 지역 미표기(None)는 제외.
        rows = [(m, o) for m, o in rows if _normalize_sido(o.region) in (region, "전국")]

    # dedup: 같은 논리 공고(_dedup_key)면 score 최고 1건 유지. NTIS 등 마감 정보 보존을
    # 위해 동점이면 deadline 있는 행 우선.
    best: dict[object, tuple[Match, Opportunity]] = {}
    for m, o in rows:
        key = _dedup_key(o)
        cur = best.get(key)
        if cur is None:
            best[key] = (m, o)
            continue
        cm, co = cur
        cand_rank = (m.score or 0, co.deadline is None and o.deadline is not None)
        cur_rank = (cm.score or 0, False)
        if cand_rank > cur_rank:
            best[key] = (m, o)

    items_all = [_build_item(m, o, company) for m, o in best.values()]

    # feasibility 필터: verdict 일치하는 것만 남김(feasibility=None인 항목은 제외)
    if effective_feasibility is not None:
        items_all = [
            i for i in items_all
            if i.feasibility is not None
            and i.feasibility["verdict"] == effective_feasibility
        ]

    if effective_sort == "feasibility":
        # verdict rank 오름차순, 동점이면 score 내림차순
        items_all.sort(
            key=lambda i: (
                _VERDICT_RANK.get(i.feasibility["verdict"] if i.feasibility else None, 3),
                -(i.score or 0),
            )
        )
    elif effective_sort == "deadline":
        # deadline asc, nulls last
        items_all.sort(key=lambda i: (i.deadline is None, i.deadline))
    elif effective_sort == "posted":
        # posted_at desc, nulls last
        items_all.sort(key=lambda i: (i.posted_at is None, i.posted_at and i.posted_at.timestamp() * -1))
    elif effective_sort == "budget":
        # budget_amount desc, nulls last
        items_all.sort(key=lambda i: (i.budget_amount is None, -(i.budget_amount or 0)))
    else:
        # score desc, nulls last (기본)
        items_all.sort(key=lambda i: (i.score is None, -(i.score or 0)))

    total = len(items_all)
    offset = (page - 1) * size
    items = items_all[offset: offset + size]

    return OpportunityList(items=items, total=total, page=page, size=size)


@router.get("/awards", response_model=AwardList)
def list_awards(
    company_id: CurrentCompany,   # auth only — awards are public, NOT company-filtered
    db: DbSession,
    q: str | None = None,
    category: str | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
) -> AwardList:
    base = select(OpportunityAward)
    if category:
        base = base.where(OpportunityAward.category == category)
    if q:
        base = base.where(or_(OpportunityAward.title.ilike(f"%{q}%"),
                              OpportunityAward.demand_agency.ilike(f"%{q}%")))
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = db.scalars(
        base.order_by(OpportunityAward.final_award_date.desc().nullslast(),
                      OpportunityAward.registered_at.desc().nullslast())
        .offset((page - 1) * size).limit(size)
    ).all()
    items = [AwardItem(
        id=str(a.id), title=a.title, category=a.category,
        winner_name=a.winner_name, winner_bizno=a.winner_bizno,
        award_amount=a.award_amount,
        award_rate=float(a.award_rate) if a.award_rate is not None else None,
        participant_count=a.participant_count, demand_agency=a.demand_agency,
        final_award_date=a.final_award_date.isoformat() if a.final_award_date else None,
        registered_at=a.registered_at.isoformat() if a.registered_at else None,
        bid_ntce_no=a.bid_ntce_no,
    ) for a in rows]
    return AwardList(items=items, total=total, page=page, size=size)


@router.get("/{opportunity_id}")
def detail(opportunity_id: uuid.UUID, company_id: CurrentCompany, db: DbSession) -> dict:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(404, "not found")
    # dedup 군집의 다른 출처(타 공고 출처) — dedup_group_id 공유 멤버의 소스.
    other_sources: list[str] = []
    if opp.dedup_group_id is not None:
        other_sources = [
            s for (s,) in db.execute(
                select(Opportunity.source)
                .distinct()
                .where(
                    Opportunity.dedup_group_id == opp.dedup_group_id,
                    Opportunity.id != opp.id,
                )
            ).all()
        ]
    company = db.get(Company, company_id)
    match = db.scalar(
        select(Match).where(Match.company_id == company_id, Match.opportunity_id == opportunity_id)
    )
    feasibility = _feasibility_dict(
        assess_feasibility(
            tech_level=company.tech_level if company else None,
            max_project_budget=company.max_project_budget if company else None,
            capable_categories=company.capable_categories if company else None,
            budget_amount=opp.budget_amount,
            category=opp.category,
        )
    )
    return {
        "opportunity": {
            "id": str(opp.id), "title": opp.title, "agency": opp.agency,
            "category": opp.category, "budget_amount": opp.budget_amount,
            "deadline": opp.deadline.isoformat() if opp.deadline else None,
            "detail_url": opp.detail_url, "source": opp.source, "status": opp.status,
            "description": opp.description, "region": opp.region,
            "posted_at": opp.posted_at.isoformat() if opp.posted_at else None,
        },
        "match": None if not match else {
            "score": match.score, "reasons": [match.reason] if match.reason else [],
            "subscore": match.subscore, "risk": match.risk,
        },
        "feasibility": feasibility,
        "other_sources": other_sources,
    }
