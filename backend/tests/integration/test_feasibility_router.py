"""통합: 수행 가능성(feasibility) — 역량 저장 + 추천 응답 검증.

- PUT /company/profile 로 역량 3필드 저장 → GET /company/profile 에 반영.
- 역량 설정 후 GET /recommendations/today feasibility 포함 확인.
- TEST_DATABASE_URL 없으면 skip.
"""
from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — integration test skipped",
)


class _TxSession:
    """commit→flush (conftest rollback이 격리 담당)."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def commit(self):
        self._s.flush()


@pytest.fixture()
def client(db_session):
    from app.api.deps import get_current_company_id  # noqa: PLC0415
    from app.db.base import get_session  # noqa: PLC0415
    from app.main import app  # noqa: PLC0415

    tx = _TxSession(db_session)

    def _override_session():
        yield tx

    app.dependency_overrides[get_session] = _override_session
    try:
        yield TestClient(app, raise_server_exceptions=True)
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_current_company_id, None)


@pytest.fixture()
def auth(client):
    """register → (headers, company_id)."""
    email = f"feasibility_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "가능성테스트기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    from app.core.security import decode_access_token  # noqa: PLC0415

    company_id = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, company_id


# ── 역량 저장 및 GET 반영 ──────────────────────────────────────────────────────

def test_put_profile_capability_fields_saved_and_returned(client, auth):
    """역량 3필드 PUT 후 GET에서 그대로 반환."""
    headers, _ = auth
    payload = {
        "tech_level": 3,
        "max_project_budget": 500_000_000,
        "capable_categories": ["물품", "용역"],
    }
    put_resp = client.put("/api/v1/company/profile", headers=headers, json=payload)
    assert put_resp.status_code == 200, put_resp.text
    body = put_resp.json()
    assert body["tech_level"] == 3
    assert body["max_project_budget"] == 500_000_000
    assert body["capable_categories"] == ["물품", "용역"]

    get_resp = client.get("/api/v1/company/profile", headers=headers)
    assert get_resp.status_code == 200, get_resp.text
    get_body = get_resp.json()
    assert get_body["tech_level"] == 3
    assert get_body["max_project_budget"] == 500_000_000
    assert get_body["capable_categories"] == ["물품", "용역"]


def test_put_profile_capability_partial_update(client, auth):
    """역량 일부만 PUT — 다른 필드(industry 등) 유지."""
    headers, _ = auth
    client.put("/api/v1/company/profile", headers=headers, json={"industry": "IT서비스"})
    resp = client.put(
        "/api/v1/company/profile",
        headers=headers,
        json={"tech_level": 4, "max_project_budget": 1_000_000_000},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["industry"] == "IT서비스"      # 기존 필드 유지
    assert body["tech_level"] == 4
    assert body["max_project_budget"] == 1_000_000_000


def test_put_profile_tech_level_validation(client, auth):
    """tech_level 범위 초과(6) → 422."""
    headers, _ = auth
    resp = client.put("/api/v1/company/profile", headers=headers, json={"tech_level": 6})
    assert resp.status_code == 422


def test_put_profile_tech_level_below_min(client, auth):
    """tech_level 범위 미달(0) → 422."""
    headers, _ = auth
    resp = client.put("/api/v1/company/profile", headers=headers, json={"tech_level": 0})
    assert resp.status_code == 422


# ── 추천 응답에 feasibility 포함 ─────────────────────────────────────────────

def test_recommendations_today_feasibility_none_without_capability(client, auth):
    """역량 미설정 시 추천 응답 feasibility=None."""
    headers, company_id = auth
    # 추천이 없으면 빈 리스트 → feasibility 확인 불가, 그냥 200 확인
    resp = client.get("/api/v1/recommendations/today", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    # 추천 없으면 빈 리스트 — 있으면 feasibility None 검증
    for item in items:
        assert item.get("feasibility") is None


def test_recommendations_today_feasibility_present_with_capability(client, auth, db_session):
    """역량 설정 후 추천 있으면 feasibility dict 포함."""
    from datetime import datetime, timezone  # noqa: PLC0415

    from app.db.models.opportunity import Match, Opportunity  # noqa: PLC0415

    headers, company_id = auth

    # 역량 설정
    client.put(
        "/api/v1/company/profile",
        headers=headers,
        json={
            "tech_level": 3,
            "max_project_budget": 1_000_000_000,
            "capable_categories": ["용역"],
        },
    )

    # 테스트용 공고 + 매칭 직접 삽입
    opp_id = uuid.uuid4()
    opp = Opportunity(
        id=opp_id,
        source="narajangter",
        source_uid=f"test_{opp_id.hex[:8]}",
        title="테스트 용역 공고",
        category="용역",
        budget_amount=500_000_000,
        status="open",
        is_canonical=True,
        deadline=datetime(2099, 12, 31, tzinfo=timezone.utc),
        raw_json={},
        content_hash="a" * 64,
    )
    db_session.add(opp)
    db_session.flush()

    match = Match(
        company_id=company_id,
        opportunity_id=opp_id,
        score=80,
        reason="테스트 매칭",
    )
    db_session.add(match)
    db_session.flush()

    resp = client.get("/api/v1/recommendations/today", headers=headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert len(items) >= 1

    target = next((i for i in items if i["opportunity_id"] == str(opp_id)), None)
    assert target is not None, "삽입한 공고가 추천에 없음"

    feas = target.get("feasibility")
    assert feas is not None, "역량 설정 시 feasibility가 None이면 안 됨"
    assert feas["verdict"] == "go"
    assert feas["label"] == "수행 가능"
    assert isinstance(feas["reasons"], list)
