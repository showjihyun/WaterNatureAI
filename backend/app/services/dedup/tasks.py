"""표시단계 dedup 배치(수집+30m, 매칭 직전). 정본: docs/04-architecture/display-dedup.md.

블로킹(마감±3d & 기관/토큰) → 유사도 → union-find → 대표 선정 →
opportunities.dedup_group_id / is_canonical 갱신 + 군집 매치를 대표로 통합.

매칭은 dedup 이후(beat +60m) is_canonical만 후보로 보므로(engine.retrieve_candidates),
이 배치가 돌면 모든 경로(추천·목록·관심·진행·브리핑)가 자동으로 대표 1건만 노출.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.celery_app import celery_app
from app.db.base import SessionLocal
from app.db.models.opportunity import Match, Opportunity
from app.services.dedup.engine import (
    DedupOpp,
    cluster_opportunities,
    pick_canonical,
    stable_group_id,
)

logger = logging.getLogger(__name__)


@celery_app.task(name="dedup.run")
def run() -> int:
    db = SessionLocal()
    try:
        return run_dedup(db)
    finally:
        db.close()


def run_dedup(db: Session) -> int:
    """열린 공고 군집화 → dedup_group_id/is_canonical 갱신 + 매치 대표 통합. 변경 행 수 반환.

    멱등: 같은 데이터면 재실행해도 group_id가 동일(멤버 집합 기반)하고 변경 0.
    """
    # raw_json(대용량 JSONB)·embedding 제외하고 필요한 컬럼만 — 메모리/IO 절약.
    rows = db.execute(
        select(
            Opportunity.id,
            Opportunity.source,
            Opportunity.title,
            Opportunity.agency,
            Opportunity.deadline,
            Opportunity.budget_amount,
            Opportunity.posted_at,
            Opportunity.description,
            Opportunity.dedup_group_id,
            Opportunity.is_canonical,
        ).where(Opportunity.status == "open")
    ).all()

    opps = [
        DedupOpp(
            id=r.id,
            source=r.source,
            title=r.title or "",
            agency=r.agency,
            deadline=r.deadline,
            budget_amount=r.budget_amount,
            posted_at=r.posted_at,
            description_len=len(r.description or ""),
        )
        for r in rows
    ]
    cur = {r.id: (r.dedup_group_id, r.is_canonical) for r in rows}

    clusters = cluster_opportunities(opps)

    updates: list[dict] = []
    dup_clusters = 0
    for members in clusters:
        if len(members) == 1:
            # 단건: 이전에 군집/비대표였다면 원복(군집 해소 케이스).
            oid = members[0].id
            group, is_canon = cur[oid]
            if group is not None or is_canon is False:
                updates.append({"id": oid, "dedup_group_id": None, "is_canonical": True})
            continue

        dup_clusters += 1
        member_ids = [m.id for m in members]
        group_id = stable_group_id(member_ids)
        canonical = pick_canonical(members)
        for m in members:
            is_canon = m.id == canonical.id
            if cur[m.id] != (group_id, is_canon):
                updates.append(
                    {"id": m.id, "dedup_group_id": group_id, "is_canonical": is_canon}
                )
        _consolidate_matches(db, member_ids, canonical.id)

    if updates:
        db.execute(update(Opportunity), updates)  # pk 기준 벌크 UPDATE
    db.commit()

    logger.info(
        "dedup.run: %d clusters(%d 중복군) · %d opportunities updated",
        len(clusters), dup_clusters, len(updates),
    )
    return len(updates)


def _consolidate_matches(db: Session, member_ids: list[uuid.UUID], canonical_id: uuid.UUID) -> None:
    """군집 내 매치를 대표로 통합 — 기업별 최고 score 1건만 대표에 남기고 나머지 삭제.

    매칭이 dedup 전에 비대표 공고에 걸려 있던 기존 데이터 보정. 멱등(이미 대표 1건이면 무동작).
    """
    matches = db.scalars(
        select(Match).where(Match.opportunity_id.in_(member_ids))
    ).all()
    if not matches:
        return

    by_company: dict[uuid.UUID, list[Match]] = defaultdict(list)
    for m in matches:
        by_company[m.company_id].append(m)

    for company_id, ms in by_company.items():
        if len(ms) == 1 and ms[0].opportunity_id == canonical_id:
            continue  # 이미 대표 1건 — 멱등
        best = max(ms, key=lambda m: m.score)
        vals = {
            "score": best.score,
            "reason": best.reason,
            "subscore": best.subscore,
            "risk": best.risk,
            "created_at": min(m.created_at for m in ms),
        }
        for m in ms:
            db.delete(m)
        db.flush()  # 유니크(company,opp) 충돌 방지 — 삭제 먼저 반영
        db.add(
            Match(id=uuid.uuid4(), company_id=company_id, opportunity_id=canonical_id, **vals)
        )
