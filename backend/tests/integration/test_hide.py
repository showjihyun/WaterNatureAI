"""통합: 추천 피드백(관심없음=hidden) — 숨김 시 /recommendations/today 제외, 복원 시 재노출.

실 PG(alembic 0007 meta) + TestClient. TEST_DATABASE_URL 없으면 skip.
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
    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def commit(self):
        self._s.flush()


@pytest.fixture()
def client(db_session):
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


@pytest.fixture()
def auth(client):
    email = f"hide_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "피드백기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    from app.core.security import decode_access_token  # noqa: PLC0415

    cid = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, cid


def _make_matched_opp(db_session, company_id) -> uuid.UUID:
    """추천에 뜨도록 opportunity + match 생성."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.db.models.opportunity import Match, Opportunity  # noqa: PLC0415

    oid = uuid.uuid4()
    db_session.add(
        Opportunity(
            id=oid, source="narajangter", source_uid=f"hide-{oid}", title="숨김 테스트 공고",
            agency="조달청", category="용역", status="open", is_canonical=True,
            deadline=datetime.now(timezone.utc) + timedelta(days=10),
            budget_raw="1억원", budget_amount=100_000_000, raw_json={},
            content_hash=f"h{oid.hex}"[:64].ljust(64, "0"),
        )
    )
    db_session.flush()
    db_session.add(Match(id=uuid.uuid4(), company_id=company_id, opportunity_id=oid, score=70))
    db_session.flush()
    return oid


def _today_ids(client, headers) -> set[str]:
    r = client.get("/api/v1/recommendations/today", headers=headers)
    assert r.status_code == 200, r.text
    return {it["opportunity_id"] for it in r.json()}


def test_hide_excludes_from_recommendations_and_unhide_restores(client, auth, db_session):
    headers, cid = auth
    oid = _make_matched_opp(db_session, cid)

    # 처음엔 추천에 노출
    assert str(oid) in _today_ids(client, headers)

    # 관심없음(사유 포함)
    r = client.post(f"/api/v1/opportunities/{oid}/hide", headers=headers, json={"reason": "category"})
    assert r.status_code == 201, r.text
    assert r.json()["reason"] == "category"

    # 추천에서 제외
    assert str(oid) not in _today_ids(client, headers)

    # 사유 저장 확인(meta)
    from sqlalchemy import select  # noqa: PLC0415

    from app.db.models.opportunity import UserOpportunityAction  # noqa: PLC0415

    act = db_session.scalar(
        select(UserOpportunityAction).where(
            UserOpportunityAction.company_id == cid,
            UserOpportunityAction.opportunity_id == oid,
            UserOpportunityAction.action_type == "hidden",
        )
    )
    assert act is not None and act.meta == {"reason": "category"}

    # 실행취소 → 다시 노출
    r2 = client.delete(f"/api/v1/opportunities/{oid}/hide", headers=headers)
    assert r2.status_code == 204
    assert str(oid) in _today_ids(client, headers)


def test_hide_is_idempotent_updates_reason(client, auth, db_session):
    headers, cid = auth
    oid = _make_matched_opp(db_session, cid)
    client.post(f"/api/v1/opportunities/{oid}/hide", headers=headers, json={"reason": "agency"})
    client.post(f"/api/v1/opportunities/{oid}/hide", headers=headers, json={"reason": "budget"})

    from sqlalchemy import func, select  # noqa: PLC0415

    from app.db.models.opportunity import UserOpportunityAction  # noqa: PLC0415

    n = db_session.scalar(
        select(func.count()).select_from(UserOpportunityAction).where(
            UserOpportunityAction.company_id == cid,
            UserOpportunityAction.opportunity_id == oid,
            UserOpportunityAction.action_type == "hidden",
        )
    )
    assert n == 1  # 멱등(행 1개)
