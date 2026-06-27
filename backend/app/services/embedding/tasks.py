"""임베딩 Celery 태스크. 멱등: content_hash==embedded_hash & 동일 버전이면 스킵.

정본: embed-worker.md §6·§7.
"""
from __future__ import annotations

from datetime import datetime, timezone

from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models.company_context import CompanyContext
from app.db.models.opportunity import Opportunity
from app.services.embedding import vectorstore
from app.services.embedding.provider import get_provider


def _embedding_text(opp: Opportunity) -> str:
    # TODO: e5 query prefix: 검색 쿼리에는 "query: " prefix 사용 권장
    parts = [f"[{opp.category}] {opp.title}" if opp.category else opp.title]
    if opp.agency:
        parts.append(f"발주/소관: {opp.agency}")
    if opp.region:
        parts.append(f"지역: {opp.region}")
    if opp.description:
        parts.append(opp.description)
    return "passage: " + "\n".join(parts)


@celery_app.task(
    name="embedding.embed_opportunity",
    bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5,
)
def embed_opportunity(self, opp_id: str) -> None:
    db = SessionLocal()
    try:
        opp = db.get(Opportunity, opp_id)
        if opp is None:
            return
        if opp.embedded_hash == opp.content_hash and opp.embedding_version == settings.embedding_version:
            return  # 멱등 스킵
        vector = get_provider().embed(_embedding_text(opp))
        # 벡터를 같은 행 embedding 컬럼에 저장(pgvector). 메타데이터는 행 컬럼 그대로.
        vectorstore.store_embedding(db, vectorstore.OPPORTUNITIES, str(opp.id), vector)
        opp.embedded_hash = opp.content_hash
        opp.embedding_version = settings.embedding_version
        opp.embedded_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


@celery_app.task(name="embedding.embed_company_context", bind=True,
                 autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def embed_company_context(self, cc_id: str) -> None:
    """company_contexts 임베딩(point id=cc.id). TODO: Context 직렬화 규칙 확정."""
    db = SessionLocal()
    try:
        cc = db.get(CompanyContext, cc_id)
        if cc is None or (cc.embedded_hash == cc.content_hash
                          and cc.embedding_version == settings.embedding_version):
            return
        text = str(cc.context_json)  # TODO: 핵심필드 자연어 직렬화(company-brain.md)
        vector = get_provider().embed(text)
        vectorstore.store_embedding(db, vectorstore.COMPANY_CONTEXTS, str(cc.id), vector)
        cc.embedded_hash = cc.content_hash
        cc.embedding_version = settings.embedding_version
        cc.embedded_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
