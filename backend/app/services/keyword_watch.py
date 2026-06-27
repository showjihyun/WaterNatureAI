"""키워드 워치 매칭 — 제목·기관·내용에 키워드가 든 공고 조회(공유 로직).

GET /watches/matches(전체 피드)와 GET /alerts(최근 키워드 새 공고)가 함께 사용.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, or_, select

from app.db.models.opportunity import Match, Opportunity, UserOpportunityAction

# 동의어 그룹 — 한 키워드가 매칭되면 같은 그룹의 다른 표현도 함께 검색(한↔영·도메인 동의어).
# 주의: 포함(substring) 매칭이라 '정수처리'는 '수처리'에 이미 포함 → 진짜 다른 표현만 등록.
_SYNONYM_GROUPS: list[set[str]] = [
    {"ai", "인공지능"},
    {"빅데이터", "bigdata", "big data"},
    {"클라우드", "cloud"},
    {"사물인터넷", "iot"},
    {"연구개발", "r&d"},
    {"메타버스", "metaverse"},
    {"수처리", "물처리"},
    {"태양광", "solar"},
]
_SYNONYMS: dict[str, set[str]] = {}
for _g in _SYNONYM_GROUPS:
    for _t in _g:
        _SYNONYMS.setdefault(_t.lower(), set()).update(_g)


def expand_keyword(kw: str) -> list[str]:
    """키워드 + 동의어(그룹에 속하면). 대소문자 무시 조회, 원형 보존."""
    terms = {kw}
    terms.update(_SYNONYMS.get(kw.lower(), set()))
    return list(terms)


def keyword_cond(kw: str):
    """키워드 1개(동의어 포함) 매칭 조건 — 제목 OR 기관 OR 내용(대소문자 무시, escape)."""
    fields = []
    for t in expand_keyword(kw):
        fields += [
            Opportunity.title.icontains(t, autoescape=True),
            Opportunity.agency.icontains(t, autoescape=True),
            Opportunity.description.icontains(t, autoescape=True),
        ]
    return or_(*fields)


def matched_keywords(o: Opportunity, keywords: list[str]) -> list[str]:
    """공고의 제목·기관·내용에 (동의어 포함) 매칭된 등록 키워드. SQL 필터와 동일 기준."""
    hay = " ".join(filter(None, [o.title, o.agency, o.description])).lower()
    return [
        kw for kw in keywords if any(t.lower() in hay for t in expand_keyword(kw))
    ]


def keyword_match_rows(
    db,
    company_id: uuid.UUID,
    keywords: list[str],
    *,
    limit: int,
    recent_days: int | None = None,
    order: str = "posted",
) -> list[tuple[Opportunity, int | None, list[str], bool]]:
    """키워드 매칭 공고 행 — (opportunity, match_score, matched_keywords, saved).

    canonical·open·마감 미경과·미숨김(hidden 제외). recent_days 지정 시 최근 수집분만.
    order="created" → 최근 수집순(created_at desc), 그 외 → 최신 게시순(posted_at desc).
    """
    if not keywords:
        return []
    now = datetime.now(timezone.utc)
    hidden = (
        select(UserOpportunityAction.opportunity_id)
        .where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.action_type == "hidden",
        )
        .scalar_subquery()
    )
    saved_ids = set(
        db.scalars(
            select(UserOpportunityAction.opportunity_id).where(
                UserOpportunityAction.company_id == company_id,
                UserOpportunityAction.action_type == "saved",
            )
        ).all()
    )
    conds = [keyword_cond(kw) for kw in keywords]
    stmt = (
        select(Opportunity, Match.score)
        .outerjoin(
            Match,
            and_(Match.opportunity_id == Opportunity.id, Match.company_id == company_id),
        )
        .where(
            or_(*conds),
            Opportunity.is_canonical.is_(True),
            Opportunity.status == "open",
            or_(Opportunity.deadline.is_(None), Opportunity.deadline >= now),
            Opportunity.id.not_in(hidden),
        )
    )
    if recent_days is not None:
        stmt = stmt.where(Opportunity.created_at >= now - timedelta(days=recent_days))
    order_col = (
        Opportunity.created_at.desc()
        if order == "created"
        else Opportunity.posted_at.desc().nullslast()
    )
    rows = db.execute(stmt.order_by(order_col).limit(limit)).all()
    return [(o, score, matched_keywords(o, keywords), o.id in saved_ids) for o, score in rows]
