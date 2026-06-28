"""키워드 워치(저장 검색). AI 매칭과 독립적으로 '제목에 키워드 포함' 공고를 포착.

- GET    /watches          : 등록한 키워드 목록(오래된순).
- POST   /watches          : 키워드 추가(2~80자, 대소문자 무시 중복 멱등, 최대 30개).
- DELETE /watches/{id}     : 키워드 삭제.
- GET    /watches/matches  : 키워드(제목 포함) 매칭 공고 피드 — canonical·open·미숨김, 최신순.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import delete, func, select

from app.api.deps import CurrentCompany, DbSession
from app.core.dates import KST
from app.db.models.accounts import Company, KeywordWatch
from app.db.models.opportunity import Opportunity
from app.schemas.opportunity import RecommendationItem
from app.services.feasibility.engine import assess_feasibility
from app.services.keyword_watch import keyword_match_rows

router = APIRouter()

_MIN_LEN = 2
_MAX_LEN = 80
_MAX_KEYWORDS = 30
_MATCH_LIMIT = 50


class KeywordWatchOut(BaseModel):
    id: uuid.UUID
    keyword: str
    created_at: datetime


class KeywordWatchIn(BaseModel):
    keyword: str


def _d_day(deadline: datetime | None) -> int | None:
    if not deadline:
        return None
    return (deadline.astimezone(KST).date() - datetime.now(KST).date()).days


def _item(
    o: Opportunity,
    score: int | None,
    company: Company | None,
    matched_keywords: list[str],
    saved: bool,
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
        matched_keywords=matched_keywords,
    )


@router.get("", response_model=list[KeywordWatchOut])
def list_watches(company_id: CurrentCompany, db: DbSession) -> list[KeywordWatchOut]:
    rows = db.scalars(
        select(KeywordWatch)
        .where(KeywordWatch.company_id == company_id)
        .order_by(KeywordWatch.created_at.asc())
    ).all()
    return [
        KeywordWatchOut(id=w.id, keyword=w.keyword, created_at=w.created_at) for w in rows
    ]


@router.post("", status_code=201, response_model=KeywordWatchOut)
def add_watch(
    body: KeywordWatchIn, company_id: CurrentCompany, db: DbSession
) -> KeywordWatchOut:
    kw = " ".join((body.keyword or "").split())  # 공백 정규화 + 트림
    if len(kw) < _MIN_LEN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "키워드는 2자 이상이어야 합니다.")
    if len(kw) > _MAX_LEN:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"키워드가 너무 깁니다(최대 {_MAX_LEN}자).")

    # 대소문자 무시 중복 → 기존 항목 반환(멱등).
    existing = db.scalar(
        select(KeywordWatch).where(
            KeywordWatch.company_id == company_id,
            func.lower(KeywordWatch.keyword) == kw.lower(),
        )
    )
    if existing is not None:
        return KeywordWatchOut(
            id=existing.id, keyword=existing.keyword, created_at=existing.created_at
        )

    count = db.scalar(
        select(func.count()).select_from(KeywordWatch).where(
            KeywordWatch.company_id == company_id
        )
    )
    if count >= _MAX_KEYWORDS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"키워드는 최대 {_MAX_KEYWORDS}개까지 등록할 수 있습니다.",
        )

    watch = KeywordWatch(company_id=company_id, keyword=kw)
    db.add(watch)
    db.commit()
    db.refresh(watch)
    return KeywordWatchOut(id=watch.id, keyword=watch.keyword, created_at=watch.created_at)


@router.delete("/{watch_id}", status_code=204)
def remove_watch(watch_id: uuid.UUID, company_id: CurrentCompany, db: DbSession) -> None:
    db.execute(
        delete(KeywordWatch).where(
            KeywordWatch.id == watch_id,
            KeywordWatch.company_id == company_id,
        )
    )
    db.commit()


@router.get("/matches", response_model=list[RecommendationItem])
def watch_matches(company_id: CurrentCompany, db: DbSession) -> list[RecommendationItem]:
    """등록 키워드가 제목·기관·내용에 포함된 공고(canonical·open·미숨김), 최신 게시순 Top-N.

    AI 매칭 점수가 있으면 함께 표시(없으면 None) — 매처가 낮게 본 공고도 포착하는 게 목적.
    """
    company = db.get(Company, company_id)
    keywords = [
        w.keyword
        for w in db.scalars(
            select(KeywordWatch).where(KeywordWatch.company_id == company_id)
        ).all()
    ]
    rows = keyword_match_rows(db, company_id, keywords, limit=_MATCH_LIMIT, order="posted")
    return [_item(o, score, company, matched, saved) for o, score, matched, saved in rows]
