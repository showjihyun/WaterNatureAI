"""통합 테스트: run_daily 매칭 파이프라인 (실제 PG + alembic 스키마).

TEST_DATABASE_URL 없으면 skip.

- 테스트 데이터: 기업(Company/ready) + CompanyContext(embedding 벡터) + Opportunity(embedding)
- run_daily 실행 (LLM·embed 모킹): matches 생성 검증
- 임계 필터: score<THRESHOLD면 match 미생성
- UPSERT 멱등: 동일 (company_id, opportunity_id) 2회 실행 → 1건 유지
- pgvector retrieve: 실제 SQL로 후보 뽑는지 포함

실행:
    TEST_DATABASE_URL=postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar \\
        pytest tests/integration/test_matching_run.py -v
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — integration test skipped",
)


# ── 픽스처: 테스트 데이터 세팅 ───────────────────────────────────────────────

@pytest.fixture()
def company_ids(db_session):
    """Company(ready) + CompanyContext(embedding 있음) 세팅. UUID만 반환."""
    from app.core.config import settings
    from app.db.models.accounts import Company
    from app.db.models.company_context import CompanyContext

    company_id = uuid.uuid4()
    company = Company(
        id=company_id,
        name="테스트기업",
        industry="IT",
        region="서울",
        onboarding_status="ready",
    )
    db_session.add(company)
    db_session.flush()

    dim = settings.embedding_dim
    embedding = [0.1] * dim

    ctx_id = uuid.uuid4()
    ctx = CompanyContext(
        id=ctx_id,
        company_id=company_id,
        context_json={
            "industry": "IT",
            "industries": ["소프트웨어"],
            "technologies": ["Python", "FastAPI"],
            "services": ["웹 개발"],
            "customers": ["공공기관"],
            "certifications": [],
            "regions": ["서울"],
            "track_records": [
                {"title": "공공 포털", "year": 2023, "client": "행안부", "summary": "..."}
            ],
            "strengths": ["공공 경험"],
            "keywords": ["Python"],
        },
        content_hash="abc123",
        embedding=embedding,
    )
    db_session.add(ctx)
    db_session.flush()

    return {"company_id": company_id, "ctx_id": ctx_id}


@pytest.fixture()
def opportunity_id(db_session):
    """status=open + embedding 있는 Opportunity 세팅. UUID만 반환."""
    import hashlib
    from datetime import datetime, timedelta, timezone

    from app.core.config import settings
    from app.db.models.opportunity import Opportunity

    dim = settings.embedding_dim
    embedding = [0.1] * dim

    opp_id = uuid.uuid4()
    content = "Python 공공 포털 개발 용역"
    content_hash = hashlib.sha256(content.encode()).hexdigest()

    opp = Opportunity(
        id=opp_id,
        source="bizinfo",
        source_uid=f"test-{opp_id}",
        title="Python 공공 포털 개발 용역",
        agency="행정안전부",
        region="서울",
        category="IT",
        description="Python FastAPI 기반 공공 포털 개발",
        status="open",
        deadline=datetime.now(timezone.utc) + timedelta(days=30),
        raw_json={"test": True},
        content_hash=content_hash,
        embedding=embedding,
    )
    db_session.add(opp)
    db_session.flush()
    return opp_id


# ── LLM 모킹 헬퍼 ────────────────────────────────────────────────────────────

def _high_score_llm(*_a, **_k):
    """항상 고점수(90) 반환하는 가짜 LLM."""
    return {
        "opportunity_id": "test",
        "subscores": {"tech": 25, "track": 22, "customer": 18, "industry": 15, "region": 10},
        "score": 90,
        "reasons": ["Python 기술 일치", "공공기관 경험"],
        "risk": "",
    }


def _low_score_llm(*_a, **_k):
    """항상 저점수(반드시 threshold 미만) 반환하는 가짜 LLM."""
    return {
        "opportunity_id": "test",
        "subscores": {"tech": 5, "track": 5, "customer": 5, "industry": 5, "region": 5},
        "score": 25,
        "reasons": [],
        "risk": "기술 미충족",
    }


# ── SessionLocal 패치 헬퍼 ────────────────────────────────────────────────────

class _NoCloseSession:
    """db_session을 감싸 close()를 no-op으로 만드는 래퍼.

    run_daily는 finally: db.close()를 호출하는데, 이게 통합테스트 공유 트랜잭션의
    연결을 닫아 DetachedInstanceError를 일으킨다. 래퍼로 이를 방지.
    """

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def close(self):
        pass  # no-op: 트랜잭션 롤백 격리를 conftest가 담당

    def rollback(self):
        pass  # no-op: 오류 시에도 conftest rollback이 정리


def _patch_session(db_session):
    """SessionLocal이 _NoCloseSession을 반환하도록 patch."""
    wrapped = _NoCloseSession(db_session)
    return patch("app.services.matching.tasks.SessionLocal", return_value=wrapped)


# ── 테스트 케이스 ─────────────────────────────────────────────────────────────

class TestRunDaily:
    def test_match_created_above_threshold(
        self, db_session, company_ids, opportunity_id
    ):
        """score≥threshold → matches 1건 생성."""
        from sqlalchemy import select

        from app.core.config import settings
        from app.db.models.opportunity import Match
        from app.services.matching.tasks import run_daily

        with _patch_session(db_session):
            result = run_daily(_llm_fn=_high_score_llm)

        assert result["processed"] >= 1
        assert result["matched"] >= 1

        matches = db_session.scalars(
            select(Match).where(
                Match.company_id == company_ids["company_id"],
                Match.opportunity_id == opportunity_id,
            )
        ).all()
        assert len(matches) == 1
        assert matches[0].score >= settings.match_threshold

    def test_no_match_below_threshold(
        self, db_session, company_ids, opportunity_id
    ):
        """score<threshold → matches 미생성."""
        from sqlalchemy import select

        from app.db.models.opportunity import Match
        from app.services.matching.tasks import run_daily

        with _patch_session(db_session):
            run_daily(_llm_fn=_low_score_llm)

        # 저점수는 threshold 미달로 skipped
        matches = db_session.scalars(
            select(Match).where(
                Match.company_id == company_ids["company_id"],
            )
        ).all()
        assert len(matches) == 0

    def test_upsert_idempotent(
        self, db_session, company_ids, opportunity_id
    ):
        """동일 (company_id, opportunity_id) 2회 실행 → 1건 유지 (ON CONFLICT UPDATE)."""
        from sqlalchemy import select

        from app.db.models.opportunity import Match
        from app.services.matching.tasks import run_daily

        with _patch_session(db_session):
            run_daily(_llm_fn=_high_score_llm)
            run_daily(_llm_fn=_high_score_llm)

        matches = db_session.scalars(
            select(Match).where(
                Match.company_id == company_ids["company_id"],
                Match.opportunity_id == opportunity_id,
            )
        ).all()
        assert len(matches) == 1

    def test_pgvector_retrieve_returns_candidate(
        self, db_session, company_ids, opportunity_id
    ):
        """retrieve_candidates가 실제 pgvector SQL로 후보를 반환한다."""
        from app.services.matching.engine import retrieve_candidates

        ctx_id = str(company_ids["ctx_id"])
        candidates = retrieve_candidates(db_session, ctx_id)

        candidate_ids = [cid for cid, _ in candidates]
        assert str(opportunity_id) in candidate_ids

    def test_company_not_ready_skipped(self, db_session, opportunity_id):
        """onboarding_status != 'ready' 인 기업은 매칭 대상에서 제외."""
        from sqlalchemy import select

        from app.db.models.accounts import Company
        from app.db.models.opportunity import Match
        from app.services.matching.tasks import run_daily

        not_ready_id = uuid.uuid4()
        not_ready_company = Company(
            id=not_ready_id,
            name="미완료기업",
            industry="IT",
            onboarding_status="profile",
        )
        db_session.add(not_ready_company)
        db_session.flush()

        with _patch_session(db_session):
            run_daily(_llm_fn=_high_score_llm)

        matches = db_session.scalars(
            select(Match).where(Match.company_id == not_ready_id)
        ).all()
        assert len(matches) == 0

    def test_reasons_and_subscore_saved(
        self, db_session, company_ids, opportunity_id
    ):
        """match에 reasons(reason 컬럼)와 subscore(JSONB)가 저장된다."""
        from sqlalchemy import select

        from app.db.models.opportunity import Match
        from app.services.matching.tasks import run_daily

        with _patch_session(db_session):
            run_daily(_llm_fn=_high_score_llm)

        match = db_session.scalars(
            select(Match).where(
                Match.company_id == company_ids["company_id"],
            )
        ).first()
        assert match is not None
        assert match.subscore is not None
        assert "tech" in match.subscore
