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


class ActionIn(BaseModel):
    type: ActionType


class StatsOut(BaseModel):
    recommended: int
    opened: int
    saved: int
    participated: int
    rates: dict[str, float]
