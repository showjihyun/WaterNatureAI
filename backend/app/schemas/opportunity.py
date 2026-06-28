"""공고/추천/액션 스키마. 정본: dashboard-api.md."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ActionType = Literal["opened", "reviewed", "saved", "participated"]


class RecommendationItem(BaseModel):
    opportunity_id: uuid.UUID
    title: str
    agency: str | None = None
    category: str | None = None
    budget_amount: int | None = None
    posted_at: datetime | None = None
    deadline: datetime | None = None
    d_day: int | None = None
    score: int | None = None
    reasons: list[str] = []
    saved: bool = False
    source: str
    other_sources: list[str] = []
    detail_url: str | None = None
    feasibility: dict | None = None  # verdict/label/reasons (수행 가능성 판단, 역량 미설정 시 None)
    matched_keywords: list[str] = []  # 키워드 워치(#5) 피드에서 매칭된 키워드(그 외 빈 리스트)
    # 설명력: 적합도 차원별 분해(tech/track/customer/industry/region) + 리스크 한 줄.
    subscore: dict | None = None
    risk: str | None = None


class OpportunityList(BaseModel):
    items: list[RecommendationItem]
    total: int
    page: int
    size: int


class AwardItem(BaseModel):
    id: str
    title: str | None = None
    category: str | None = None
    winner_name: str | None = None
    winner_bizno: str | None = None
    award_amount: int | None = None
    award_rate: float | None = None
    participant_count: int | None = None
    demand_agency: str | None = None
    final_award_date: str | None = None   # ISO date
    registered_at: str | None = None      # ISO datetime
    bid_ntce_no: str | None = None


class AwardList(BaseModel):
    items: list[AwardItem]
    total: int
    page: int
    size: int


class ActionIn(BaseModel):
    type: ActionType


class StatsOut(BaseModel):
    recommended: int
    opened: int
    saved: int
    participated: int
    rates: dict[str, float]


# ── 데이터 수집 통계(대시보드 '데이터 수집 현황' 섹션) ───────────────────────────
class TrendPoint(BaseModel):
    label: str   # 축 라벨 (일=MM/DD, 주=주시작 MM/DD, 월=YY/MM, 년=YYYY)
    count: int


class SourceCount(BaseModel):
    source: str  # 소스 코드(narajangter 등) — 라벨 매핑은 프론트 sourceLabel
    count: int


class CategoryCount(BaseModel):
    category: str
    count: int


class BudgetBucket(BaseModel):
    label: str
    count: int


class BudgetStats(BaseModel):
    total: int               # 예산 합계(예산 있는 공고)
    avg: int                 # 평균 예산
    count_with_budget: int   # 예산 표기된 공고 수
    buckets: list[BudgetBucket]


class AwardStats(BaseModel):
    count: int
    avg_rate: float | None = None     # 평균 낙찰률(%)
    avg_amount: int | None = None     # 평균 낙찰가
    total_amount: int | None = None   # 낙찰가 합계


class CollectionSummary(BaseModel):
    new_today: int      # 오늘(KST) 신규 수집 공고
    new_7d: int         # 최근 7일 신규 수집 공고
    total: int          # 누적 공고(대표·canonical)
    awards_total: int   # 누적 낙찰


class CollectionStatsOut(BaseModel):
    as_of: datetime
    summary: CollectionSummary
    trends: dict[str, list[TrendPoint]]   # day/week/month/year → 기간별 수집 추세
    by_source: list[SourceCount]
    by_category: list[CategoryCount]
    budget: BudgetStats
    awards: AwardStats
