"""매칭 Celery 태스크 — 05:50 sweep, 07:00 일일 매칭.

정본: matching-engine.md §6, db-schema §9(sweep).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select, update

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models.accounts import Company
from app.db.models.company_context import CompanyContext
from app.db.models.opportunity import Match, Opportunity
from app.services.llm import resolve_llm_fn
from app.services.matching.engine import _compute_rule_presets, retrieve_candidates, score_match

logger = logging.getLogger(__name__)

# _llm_fn 기본값 sentinel: 미지정이면 활성 공급자에서 LLM 해석,
# 명시적 None이면 규칙 전용(seed/테스트 호환).
_UNSET: object = object()


@celery_app.task(name="matching.sweep_opportunity_status")
def sweep_opportunity_status() -> int:
    """마감 경과 open→closed (now()는 IMMUTABLE 아님 → 생성열 불가, 배치로 전이)."""
    db = SessionLocal()
    try:
        result = db.execute(
            update(Opportunity)
            .where(
                Opportunity.status == "open",
                Opportunity.deadline.is_not(None),
                Opportunity.deadline < datetime.now(timezone.utc),
            )
            .values(status="closed")
        )
        db.commit()
        return result.rowcount or 0
    finally:
        db.close()


@celery_app.task(name="matching.run_daily")
def run_daily(*, company_id: str | None = None, _llm_fn: object = _UNSET) -> dict:
    """활성·구독 기업 × 신규/변경 공고 매칭 → matches UPSERT(≥THRESHOLD).

    활성 기업(onboarding_status='ready') 전체를 순회. company_id 지정 시 **그 기업만**
    매칭(온보딩 직후 단일 기업 즉시 매칭용 — 전체 run보다 훨씬 빠름).
    각 기업의 company_context(embedding 있는 최신 행) → retrieve_candidates(pgvector) →
    규칙 점수 계산 → **규칙 상위 K개만 LLM 재평가**(settings.match_llm_top_k; 비용·지연 제어) →
    score>=settings.match_threshold 면 matches UPSERT.

    UNIQUE(company_id, opportunity_id) 제약으로 멱등(ON CONFLICT UPDATE score/reason/subscore).

    Args:
        _llm_fn: 미지정 시 활성 공급자(app_settings('llm'))에서 LLM 해석(키 없으면 규칙 전용).
                 명시적 None이면 규칙 전용(seed/테스트). 함수 주입 시 그 함수 사용(테스트 모킹).

    Returns:
        dict: {"processed": <기업 수>, "matched": <upsert 수>, "skipped": <임계미달 수>}
    """
    from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: PLC0415

    db = SessionLocal()
    processed = 0
    matched = 0
    skipped = 0

    # 활성 LLM 함수 해석(1회). 미지정=활성 공급자, None=규칙전용, 함수=주입.
    active_llm: Callable | None
    if _llm_fn is _UNSET:
        active_llm = resolve_llm_fn(db)
    elif callable(_llm_fn):
        active_llm = _llm_fn
    else:
        active_llm = None
    top_k = settings.match_llm_top_k

    try:
        # 활성 기업: onboarding_status='ready' 인 기업만 매칭 대상
        company_q = select(Company).where(Company.onboarding_status == "ready")
        if company_id is not None:
            company_q = company_q.where(Company.id == uuid.UUID(company_id))
        companies = db.scalars(company_q).all()

        for company in companies:
            processed += 1
            company_id = company.id

            # 해당 기업의 최신 company_context (embedding이 있어야 retrieve 가능)
            ctx_row = db.scalars(
                select(CompanyContext)
                .where(
                    CompanyContext.company_id == company_id,
                    CompanyContext.embedding.isnot(None),
                )
                .order_by(CompanyContext.created_at.desc())
                .limit(1)
            ).first()

            if ctx_row is None:
                logger.debug("company %s: company_context 없음 — 스킵", company_id)
                continue

            ctx_id = str(ctx_row.id)
            ctx_json: dict = ctx_row.context_json or {}

            # ① 후보 검색 (pgvector) → (id, similarity) 리스트
            candidates = retrieve_candidates(db, ctx_id)
            if not candidates:
                logger.debug("company %s: 후보 공고 없음", company_id)
                continue

            candidate_ids = [cid for cid, _ in candidates]
            sim_map: dict[str, float] = {cid: sim for cid, sim in candidates}

            # 공고 정보 일괄 조회
            opp_rows = db.scalars(
                select(Opportunity).where(
                    Opportunity.id.in_([uuid.UUID(oid) for oid in candidate_ids])
                )
            ).all()
            opp_map = {str(opp.id): opp for opp in opp_rows}

            # ② 후보별 규칙 presets 선계산(키 불필요) → 상위 K개만 LLM 재평가
            prepared: list[dict] = []
            for opp_id_str in candidate_ids:
                opp = opp_map.get(opp_id_str)
                if opp is None:
                    continue
                opp_dict = {
                    "id": str(opp.id),
                    "title": opp.title or "",
                    "agency": opp.agency,
                    "region": opp.region,
                    "category": opp.category,
                    "description": opp.description,
                }
                presets = _compute_rule_presets(ctx_json, opp_dict)
                prepared.append({
                    "id": opp_id_str,
                    "opp": opp,
                    "opp_dict": opp_dict,
                    "presets": presets,
                    "sim": sim_map.get(opp_id_str),
                    "rule_subtotal": sum(presets.values()),
                })

            # 규칙 점수 상위 K개만 LLM 재평가(active_llm 없으면 전부 규칙 전용).
            llm_ids: set[str] = set()
            if active_llm is not None and prepared:
                ranked = sorted(
                    prepared,
                    key=lambda r: (r["rule_subtotal"], r["sim"] or 0.0),
                    reverse=True,
                )
                limit = top_k if top_k and top_k > 0 else len(ranked)
                llm_ids = {r["id"] for r in ranked[:limit]}

            # ③ score_match — 상위 K = LLM+규칙 하이브리드, 나머지 = 규칙 전용
            for row in prepared:
                opp = row["opp"]
                opp_id_str = row["id"]
                fn = active_llm if opp_id_str in llm_ids else None
                try:
                    result = score_match(
                        ctx_json,
                        row["opp_dict"],
                        row["presets"],
                        llm_complete_json=fn,
                        similarity=row["sim"],
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning(
                        "score_match 실패 (company=%s, opp=%s): %s",
                        company_id, opp_id_str, exc,
                    )
                    continue

                # ④ 임계 필터
                if result.score < settings.match_threshold:
                    skipped += 1
                    continue

                # ⑤ matches UPSERT (UNIQUE(company_id, opportunity_id) → ON CONFLICT UPDATE)
                reason_text = "; ".join(result.reasons) if result.reasons else None
                stmt = (
                    pg_insert(Match)
                    .values(
                        id=uuid.uuid4(),
                        company_id=company_id,
                        opportunity_id=opp.id,
                        score=result.score,
                        reason=reason_text,
                        subscore=result.subscore,
                        risk=result.risk,
                        created_at=datetime.now(timezone.utc),
                    )
                    .on_conflict_do_update(
                        constraint="uq_matches_company_opp",
                        set_={
                            "score": result.score,
                            "reason": reason_text,
                            "subscore": result.subscore,
                            "risk": result.risk,
                        },
                    )
                )
                db.execute(stmt)
                matched += 1

        db.commit()
        logger.info(
            "run_daily 완료: processed=%d, matched=%d, skipped=%d",
            processed, matched, skipped,
        )
        return {"processed": processed, "matched": matched, "skipped": skipped}

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
