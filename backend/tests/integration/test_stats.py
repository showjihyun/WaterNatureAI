"""통합: /dashboard/stats 퍼널 통계.

실 PG(alembic 스키마) + TestClient. 외부 실호출 없음.
recommended = matches(canonical·open) count 기반 검증 — notified 아님.

TEST_DATABASE_URL 없으면 skip.
"""
from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — integration test skipped",
)


# ── helpers ────────────────────────────────────────────────────────────────

class _TxSession:
    """공유 트랜잭션 보존 래퍼: commit→flush (conftest rollback이 격리 담당)."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def commit(self):
        self._s.flush()


# ── fixtures ───────────────────────────────────────────────────────────────

@pytest.fixture()
def client(db_session):
    """get_session을 공유 트랜잭션(commit→flush)으로 오버라이드한 TestClient."""
    from app.api.deps import get_current_company_id  # noqa: PLC0415
    from app.db.base import get_session  # noqa: PLC0415
    from app.main import app  # noqa: PLC0415

    tx = _TxSession(db_session)

    def _override_session():
        yield tx

    app.dependency_overrides[get_session] = _override_session
    try:
        from fastapi.testclient import TestClient
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_current_company_id, None)


@pytest.fixture()
def auth(client):
    """register → (headers, company_id)."""
    email = f"stats_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "통계테스트기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    from app.core.security import decode_access_token  # noqa: PLC0415

    company_id = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, company_id


@pytest.fixture()
def other_auth(client):
    """타사 격리 검증용 별도 회사."""
    email = f"other_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "타사기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    from app.core.security import decode_access_token  # noqa: PLC0415

    company_id = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, company_id


def _seed_opportunity(db, *, is_canonical: bool = True, status: str = "open") -> uuid.UUID:
    """테스트용 Opportunity 시드. source='narajangter'(마이그레이션 0001 seed)."""
    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    opp_id = uuid.uuid4()
    opp = Opportunity(
        id=opp_id,
        source="narajangter",
        source_uid=f"test-{opp_id.hex[:8]}",
        title=f"테스트공고-{opp_id.hex[:6]}",
        is_canonical=is_canonical,
        status=status,
        content_hash=opp_id.hex,
        raw_json={},
    )
    db.add(opp)
    db.flush()
    return opp_id


def _seed_match(db, *, company_id: uuid.UUID, opportunity_id: uuid.UUID) -> None:
    from app.db.models.opportunity import Match  # noqa: PLC0415

    m = Match(
        company_id=company_id,
        opportunity_id=opportunity_id,
        score=80,
    )
    db.add(m)
    db.flush()


def _seed_action(
    db,
    *,
    company_id: uuid.UUID,
    opportunity_id: uuid.UUID,
    action_type: str,
) -> None:
    from app.db.models.opportunity import UserOpportunityAction  # noqa: PLC0415

    a = UserOpportunityAction(
        company_id=company_id,
        opportunity_id=opportunity_id,
        action_type=action_type,
    )
    db.add(a)
    db.flush()


# ── tests ──────────────────────────────────────────────────────────────────

def test_stats_recommended_from_matches(client, auth, db_session):
    """matches 3건 + opened 1 + saved 1 → recommended=3, 열람=engagement distinct=2.

    opened(열람)는 engagement(opened|saved|participated|reviewed) distinct 공고 수 —
    opp0(opened)+opp1(saved) = 2건. 관심(saved)=1, 참여=0. 단조성(2≥1≥0) 성립.
    """
    headers, company_id = auth

    # 공고 3건(canonical·open) + match 3건
    opp_ids = [_seed_opportunity(db_session) for _ in range(3)]
    for opp_id in opp_ids:
        _seed_match(db_session, company_id=company_id, opportunity_id=opp_id)

    # 액션: 첫 공고 opened, 두 번째 saved
    _seed_action(db_session, company_id=company_id, opportunity_id=opp_ids[0], action_type="opened")
    _seed_action(db_session, company_id=company_id, opportunity_id=opp_ids[1], action_type="saved")

    resp = client.get("/api/v1/dashboard/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["recommended"] == 3
    assert body["opened"] == 2  # engagement distinct: opp0(opened)+opp1(saved)
    assert body["saved"] == 1
    assert body["participated"] == 0
    # 단조성: 열람 ≥ 관심 ≥ 참여
    assert body["opened"] >= body["saved"] >= body["participated"]
    assert body["rates"]["open"] == round(2 / 3, 4)
    assert body["rates"]["save"] == round(1 / 3, 4)
    assert body["rates"]["participate"] == 0.0


def test_stats_non_canonical_excluded(client, auth, db_session):
    """is_canonical=False인 match는 recommended에서 제외."""
    headers, company_id = auth

    # canonical=True 2건, canonical=False 1건
    opp_canonical1 = _seed_opportunity(db_session, is_canonical=True, status="open")
    opp_canonical2 = _seed_opportunity(db_session, is_canonical=True, status="open")
    opp_non_canonical = _seed_opportunity(db_session, is_canonical=False, status="open")

    for opp_id in (opp_canonical1, opp_canonical2, opp_non_canonical):
        _seed_match(db_session, company_id=company_id, opportunity_id=opp_id)

    resp = client.get("/api/v1/dashboard/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # non-canonical 제외 → 2건만
    assert body["recommended"] == 2


def test_stats_closed_opportunity_excluded(client, auth, db_session):
    """status=closed인 match는 recommended에서 제외."""
    headers, company_id = auth

    opp_open = _seed_opportunity(db_session, is_canonical=True, status="open")
    opp_closed = _seed_opportunity(db_session, is_canonical=True, status="closed")

    for opp_id in (opp_open, opp_closed):
        _seed_match(db_session, company_id=company_id, opportunity_id=opp_id)

    resp = client.get("/api/v1/dashboard/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # closed 제외 → 1건만
    assert body["recommended"] == 1


def test_stats_company_isolation(client, auth, other_auth, db_session):
    """타사 matches는 자사 recommended에 잡히지 않음."""
    headers, company_id = auth
    _, other_company_id = other_auth

    # 자사 match 1건, 타사 match 2건
    opp_mine = _seed_opportunity(db_session)
    _seed_match(db_session, company_id=company_id, opportunity_id=opp_mine)

    opp_other1 = _seed_opportunity(db_session)
    opp_other2 = _seed_opportunity(db_session)
    _seed_match(db_session, company_id=other_company_id, opportunity_id=opp_other1)
    _seed_match(db_session, company_id=other_company_id, opportunity_id=opp_other2)

    resp = client.get("/api/v1/dashboard/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # 타사 2건 제외 → 자사 1건만
    assert body["recommended"] == 1


def test_stats_zero_recommended_rates_fallback(client, auth, db_session):
    """matches 0건 → recommended=0, rates는 0(분모 1 폴백)."""
    headers, _ = auth

    resp = client.get("/api/v1/dashboard/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["recommended"] == 0
    assert body["rates"]["open"] == 0.0
    assert body["rates"]["save"] == 0.0
    assert body["rates"]["participate"] == 0.0


def test_stats_funnel_monotonic_without_opened(client, auth, db_session):
    """열람 액션 없이 저장·참여만 한 공고 → 열람≥관심≥참여 단조성 보장(회귀).

    버그: opened 미기록 시 열람=0인데 관심=1·참여=1로 퍼널이 비단조였음.
    수정: opened=engagement(opened|saved|participated|reviewed) distinct 공고 수.
    """
    headers, company_id = auth

    opp = _seed_opportunity(db_session)
    _seed_match(db_session, company_id=company_id, opportunity_id=opp)
    # 'opened' 액션 없이 saved + participated 만 기록(같은 공고)
    _seed_action(db_session, company_id=company_id, opportunity_id=opp, action_type="saved")
    _seed_action(db_session, company_id=company_id, opportunity_id=opp, action_type="participated")

    resp = client.get("/api/v1/dashboard/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["opened"] == 1, "engagement 있는 공고는 열람으로 집계되어야 함"
    assert body["saved"] == 1
    assert body["participated"] == 1
    assert body["opened"] >= body["saved"] >= body["participated"], "퍼널 단조성 위반"


def test_stats_notified_action_not_counted_as_recommended(client, auth, db_session):
    """notified 액션은 recommended에 영향을 주지 않음(웹 퍼널 분리)."""
    headers, company_id = auth

    # matches 0건, notified 액션 5건
    opp_id = _seed_opportunity(db_session)
    for _ in range(5):
        _seed_action(
            db_session,
            company_id=company_id,
            opportunity_id=opp_id,
            action_type="notified",
        )

    resp = client.get("/api/v1/dashboard/stats", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()

    # notified는 recommended 분모가 아님
    assert body["recommended"] == 0
