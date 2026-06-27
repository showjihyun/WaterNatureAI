"""통합: 진행 관리 파이프라인(pursuits) — 추가→조회→단계이동→제출(참여기록)→삭제.

실 PG(alembic 스키마, 0006 pursuits) + TestClient. TEST_DATABASE_URL 없으면 skip.
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
    email = f"pursuit_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "파이프라인기업"},
    )
    assert resp.status_code == 201, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


def _make_opp(db_session) -> uuid.UUID:
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    oid = uuid.uuid4()
    db_session.add(
        Opportunity(
            id=oid, source="narajangter", source_uid=f"pur-{oid}", title="파이프라인 공고",
            agency="조달청", category="용역", status="open", is_canonical=True,
            deadline=datetime.now(timezone.utc) + timedelta(days=7),
            budget_raw="1억원", budget_amount=100_000_000, raw_json={},
            content_hash=f"h{oid.hex}"[:64].ljust(64, "0"),
        )
    )
    db_session.flush()
    return oid


def _participated_count(db_session, company_id, oid) -> int:
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.db.models.opportunity import UserOpportunityAction  # noqa: PLC0415

    return db_session.scalar(
        select(func.count()).select_from(UserOpportunityAction).where(
            UserOpportunityAction.company_id == company_id,
            UserOpportunityAction.opportunity_id == oid,
            UserOpportunityAction.action_type == "participated",
        )
    )


def test_pursuit_flow_add_move_submit_delete(client, auth, db_session):
    from app.core.security import decode_access_token  # noqa: PLC0415

    company_id = uuid.UUID(decode_access_token(auth["Authorization"].split()[1])["company_id"])
    oid = _make_opp(db_session)

    # 추가(기본 reviewing)
    r1 = client.post("/api/v1/pursuits", headers=auth, json={"opportunity_id": str(oid)})
    assert r1.status_code == 201, r1.text
    assert r1.json()["stage"] == "reviewing" and r1.json()["created"] is True

    # 멱등: 재추가 → created False
    r1b = client.post("/api/v1/pursuits", headers=auth, json={"opportunity_id": str(oid)})
    assert r1b.json()["created"] is False

    # 조회
    r2 = client.get("/api/v1/pursuits", headers=auth)
    assert r2.status_code == 200
    items = r2.json()
    assert len(items) == 1
    assert items[0]["stage"] == "reviewing"
    assert items[0]["opportunity"]["opportunity_id"] == str(oid)

    # 제출 단계로 이동 → participated 기록
    assert _participated_count(db_session, company_id, oid) == 0
    r3 = client.patch(f"/api/v1/pursuits/{oid}", headers=auth, json={"stage": "submitted"})
    assert r3.status_code == 200 and r3.json()["stage"] == "submitted"
    assert _participated_count(db_session, company_id, oid) == 1

    # 잘못된 단계 거부
    r4 = client.patch(f"/api/v1/pursuits/{oid}", headers=auth, json={"stage": "bogus"})
    assert r4.status_code == 400

    # 삭제
    r5 = client.delete(f"/api/v1/pursuits/{oid}", headers=auth)
    assert r5.status_code == 204
    assert client.get("/api/v1/pursuits", headers=auth).json() == []


def test_pursuit_add_at_submitted_records_participation(client, auth, db_session):
    from app.core.security import decode_access_token  # noqa: PLC0415

    company_id = uuid.UUID(decode_access_token(auth["Authorization"].split()[1])["company_id"])
    oid = _make_opp(db_session)
    r = client.post(
        "/api/v1/pursuits", headers=auth,
        json={"opportunity_id": str(oid), "stage": "submitted"},
    )
    assert r.status_code == 201
    assert _participated_count(db_session, company_id, oid) == 1
