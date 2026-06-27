"""통합: GET /saved (관심 공고함) — 저장→조회→해제.

실 PG(alembic 스키마, sources 시드) + TestClient. TEST_DATABASE_URL 없으면 skip.
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
    """공유 트랜잭션 보존 래퍼: commit→flush (conftest rollback이 격리 담당)."""

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
    email = f"saved_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "관심테스트기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _make_opp(db_session, *, title: str) -> uuid.UUID:
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    oid = uuid.uuid4()
    db_session.add(
        Opportunity(
            id=oid,
            source="narajangter",
            source_uid=f"saved-{oid}",
            title=title,
            agency="조달청",
            category="용역",
            status="open",
            is_canonical=True,
            deadline=datetime.now(timezone.utc) + timedelta(days=10),
            budget_raw="1억원",
            budget_amount=100_000_000,
            raw_json={},
            content_hash=f"h{oid.hex}"[:64].ljust(64, "0"),
        )
    )
    db_session.flush()
    return oid


def test_saved_flow_save_list_unsave(client, auth, db_session):
    oid = _make_opp(db_session, title="관심 등록 테스트 공고")

    # 처음엔 비어 있음
    r0 = client.get("/api/v1/saved", headers=auth)
    assert r0.status_code == 200, r0.text
    assert r0.json() == []

    # 저장(♥)
    r1 = client.post(
        f"/api/v1/opportunities/{oid}/actions", headers=auth, json={"type": "saved"}
    )
    assert r1.status_code == 201, r1.text

    # 관심 공고함에 노출(saved=True)
    r2 = client.get("/api/v1/saved", headers=auth)
    assert r2.status_code == 200, r2.text
    items = r2.json()
    assert len(items) == 1
    assert items[0]["opportunity_id"] == str(oid)
    assert items[0]["title"] == "관심 등록 테스트 공고"
    assert items[0]["saved"] is True
    assert items[0]["d_day"] is not None

    # 해제 → 다시 비어 있음
    r3 = client.delete(f"/api/v1/opportunities/{oid}/actions/saved", headers=auth)
    assert r3.status_code == 204, r3.text
    r4 = client.get("/api/v1/saved", headers=auth)
    assert r4.json() == []


def test_saved_excludes_other_company(client, auth, db_session):
    """다른 회사가 저장한 공고는 내 관심함에 보이지 않음(테넌트 격리)."""
    oid = _make_opp(db_session, title="타사 저장 공고")
    # 내 회사로는 저장 안 함 → 빈 목록
    r = client.get("/api/v1/saved", headers=auth)
    assert r.status_code == 200
    assert all(it["opportunity_id"] != str(oid) for it in r.json())
