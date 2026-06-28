"""대시보드 통계(퍼널 + 데이터 수집 현황). dashboard-api §6."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter
from sqlalchemy import Date, and_, cast, func, select

from app.api.deps import CurrentCompany, DbSession
from app.db.models.opportunity import (
    Match,
    Opportunity,
    OpportunityAward,
    UserOpportunityAction,
)
from app.schemas.opportunity import (
    AwardStats,
    BudgetBucket,
    BudgetStats,
    CategoryCount,
    CollectionStatsOut,
    CollectionSummary,
    SourceCount,
    StatsOut,
    TrendPoint,
)

router = APIRouter()

KST = timezone(timedelta(hours=9))


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


# 예산 규모 분포 경계(원). 1억 / 10억 / 50억.
_BUDGET_EDGES = (100_000_000, 1_000_000_000, 5_000_000_000)


def _month_keys(today: "datetime", n: int) -> list[tuple[int, int]]:
    """오늘 기준 최근 n개월의 (연, 월) 목록(오래된 순)."""
    yy, mm = today.year, today.month
    out: list[tuple[int, int]] = []
    for _ in range(n):
        out.append((yy, mm))
        mm -= 1
        if mm == 0:
            mm, yy = 12, yy - 1
    return list(reversed(out))


@router.get("/collection", response_model=CollectionStatsOut)
def collection_stats(company_id: CurrentCompany, db: DbSession) -> CollectionStatsOut:
    """데이터 수집 현황 — 요약·기간별 추세(일/주/월/년)·소스/분야/예산/낙찰 분석.

    수집(collected_at) 기준 시장 데이터(회사 스코프 아님, 인증만). 추세 4종을 한 번에
    내려주고 프론트가 토글만 전환(재요청 없음). 추세 버킷팅은 KST 기준.
    """
    now_kst = datetime.now(KST)
    today = now_kst.date()
    today_start = now_kst.replace(hour=0, minute=0, second=0, microsecond=0)
    canonical = Opportunity.is_canonical.is_(True)

    # ── 요약 ──────────────────────────────────────────────────────────────────
    total = db.scalar(select(func.count()).select_from(Opportunity).where(canonical)) or 0
    new_today = db.scalar(
        select(func.count()).select_from(Opportunity)
        .where(canonical, Opportunity.collected_at >= today_start)
    ) or 0
    new_7d = db.scalar(
        select(func.count()).select_from(Opportunity)
        # "최근 7일" = 오늘 포함 7개 캘린더일(KST) — new_today와 동일하게 자정 경계.
        .where(canonical, Opportunity.collected_at >= today_start - timedelta(days=6))
    ) or 0
    awards_total = db.scalar(select(func.count()).select_from(OpportunityAward)) or 0

    # ── 기간별 수집 추세(일/주/월/년) ─────────────────────────────────────────────
    # Postgres에서 collected_at을 KST 일자로 GROUP BY(전건 파이썬 적재 방지 — 전송량이
    # 행수가 아닌 distinct-day 수에만 비례). 주/월/년은 일 집계에서 파이썬 재합산.
    kst_day = cast(func.timezone("Asia/Seoul", Opportunity.collected_at), Date)
    day_rows = db.execute(
        select(kst_day.label("d"), func.count())
        .where(canonical, Opportunity.collected_at >= now_kst - timedelta(days=370 * 5))
        .group_by(kst_day)
    ).all()
    day_c: dict = {}
    week_c: Counter = Counter()
    month_c: Counter = Counter()
    year_c: Counter = Counter()
    for d, c in day_rows:
        day_c[d] = c
        week_c[d - timedelta(days=d.weekday())] += c   # 주 시작(월요일)
        month_c[(d.year, d.month)] += c
        year_c[d.year] += c

    days = [today - timedelta(days=i) for i in range(13, -1, -1)]       # 최근 14일
    this_week = today - timedelta(days=today.weekday())
    weeks = [this_week - timedelta(weeks=i) for i in range(11, -1, -1)]  # 최근 12주
    months = _month_keys(now_kst, 12)                                   # 최근 12개월
    years = list(range(today.year - 4, today.year + 1))                 # 최근 5년

    trends = {
        "day": [TrendPoint(label=f"{d.month:02d}/{d.day:02d}", count=day_c.get(d, 0)) for d in days],
        "week": [TrendPoint(label=f"{w.month:02d}/{w.day:02d}", count=week_c.get(w, 0)) for w in weeks],
        "month": [TrendPoint(label=f"{y % 100:02d}/{m:02d}", count=month_c.get((y, m), 0)) for (y, m) in months],
        "year": [TrendPoint(label=str(y), count=year_c.get(y, 0)) for y in years],
    }

    # ── 소스별 분포 ────────────────────────────────────────────────────────────
    by_source = [
        SourceCount(source=s, count=c)
        for s, c in db.execute(
            select(Opportunity.source, func.count()).where(canonical)
            .group_by(Opportunity.source).order_by(func.count().desc())
        ).all()
    ]

    # ── 분야(업종)별 Top 8 ────────────────────────────────────────────────────
    by_category = [
        CategoryCount(category=c, count=n)
        for c, n in db.execute(
            select(Opportunity.category, func.count())
            .where(canonical, Opportunity.category.isnot(None), Opportunity.category != "")
            .group_by(Opportunity.category).order_by(func.count().desc()).limit(8)
        ).all()
    ]

    # ── 예산 규모: 합계/평균/표기수 + 구간 분포 ─────────────────────────────────
    has_budget = and_(canonical, Opportunity.budget_amount.isnot(None), Opportunity.budget_amount > 0)
    e0, e1, e2 = _BUDGET_EDGES
    b = db.execute(
        select(
            func.coalesce(func.sum(Opportunity.budget_amount), 0),
            func.coalesce(func.avg(Opportunity.budget_amount), 0),
            func.count(),
            func.count().filter(Opportunity.budget_amount < e0),
            func.count().filter(and_(Opportunity.budget_amount >= e0, Opportunity.budget_amount < e1)),
            func.count().filter(and_(Opportunity.budget_amount >= e1, Opportunity.budget_amount < e2)),
            func.count().filter(Opportunity.budget_amount >= e2),
        ).where(has_budget)
    ).one()
    budget = BudgetStats(
        total=int(b[0]), avg=int(b[1]), count_with_budget=int(b[2]),
        buckets=[
            BudgetBucket(label="1억 미만", count=int(b[3])),
            BudgetBucket(label="1~10억", count=int(b[4])),
            BudgetBucket(label="10~50억", count=int(b[5])),
            BudgetBucket(label="50억 이상", count=int(b[6])),
        ],
    )

    # ── 낙찰 통계 ──────────────────────────────────────────────────────────────
    a = db.execute(
        select(
            func.count(),
            func.avg(OpportunityAward.award_rate),
            func.avg(OpportunityAward.award_amount),
            func.sum(OpportunityAward.award_amount),
        )
    ).one()
    awards = AwardStats(
        count=int(a[0]),
        avg_rate=round(float(a[1]), 2) if a[1] is not None else None,
        avg_amount=int(a[2]) if a[2] is not None else None,
        total_amount=int(a[3]) if a[3] is not None else None,
    )

    return CollectionStatsOut(
        as_of=now_kst,
        summary=CollectionSummary(
            new_today=new_today, new_7d=new_7d, total=total, awards_total=awards_total
        ),
        trends=trends, by_source=by_source, by_category=by_category,
        budget=budget, awards=awards,
    )
