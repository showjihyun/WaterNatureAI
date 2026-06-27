"""통합: 마감 리마인더(D-3) — GET /reminders 조회 + send_deadline_reminders 멱등.

실 PG(alembic 0010 deadline_reminder_days) + TestClient/모킹. TEST_DATABASE_URL 없으면 skip.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — integration test skipped",
)


# ── 공유 헬퍼 ────────────────────────────────────────────────────────────────

class _TxSession:
    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def commit(self):
        self._s.flush()


def _seed_opp(db_session, title: str, *, days: int | None, status: str = "open",
              canonical: bool = True) -> uuid.UUID:
    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    oid = uuid.uuid4()
    deadline = None if days is None else datetime.now(timezone.utc) + timedelta(days=days)
    db_session.add(
        Opportunity(
            id=oid, source="narajangter", source_uid=f"rem-{oid}", title=title,
            agency="기관", category="용역", status=status, is_canonical=canonical,
            deadline=deadline, budget_raw="1억원", budget_amount=100_000_000, raw_json={},
            content_hash=f"h{oid.hex}"[:64].ljust(64, "0"),
        )
    )
    db_session.flush()
    return oid


def _save(db_session, cid, oid) -> None:
    from app.db.models.opportunity import UserOpportunityAction  # noqa: PLC0415

    db_session.add(UserOpportunityAction(company_id=cid, opportunity_id=oid, action_type="saved"))
    db_session.flush()


def _pursue(db_session, cid, oid, stage: str = "reviewing") -> None:
    from app.db.models.opportunity import Pursuit  # noqa: PLC0415

    db_session.add(Pursuit(company_id=cid, opportunity_id=oid, stage=stage))
    db_session.flush()


# ── GET /reminders (인앱 마감 임박) ──────────────────────────────────────────

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
    email = f"rem_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "리마인더기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    from app.core.security import decode_access_token  # noqa: PLC0415

    cid = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, cid


def _reminders(client, headers) -> list[dict]:
    r = client.get("/api/v1/reminders", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def test_lists_tracked_due_soon_ordered(client, auth, db_session):
    headers, cid = auth
    a = _seed_opp(db_session, "관심 D-2", days=2)
    b = _seed_opp(db_session, "관심 D-9(윈도우 밖)", days=9)
    _seed_opp(db_session, "비추적 D-1", days=1)  # c — 추적 안 함
    d = _seed_opp(db_session, "진행 D-1", days=1)
    _save(db_session, cid, a)
    _save(db_session, cid, b)
    _pursue(db_session, cid, d)

    items = _reminders(client, headers)
    titles = [it["opportunity"]["title"] for it in items]
    # 임박순(D-1 먼저, D-2 다음) — 윈도우(3) 밖/비추적 제외
    assert titles == ["진행 D-1", "관심 D-2"]
    via = {it["opportunity"]["title"]: it["tracked_via"] for it in items}
    assert via["진행 D-1"] == "pursuit" and via["관심 D-2"] == "saved"


def test_window_from_settings(client, auth, db_session):
    headers, cid = auth
    e = _seed_opp(db_session, "관심 D-5", days=5)
    _save(db_session, cid, e)

    # 기본 윈도우 3 → 미포함
    assert _reminders(client, headers) == []

    # D-7 로 넓히면 포함
    client.put("/api/v1/settings/notification", headers=headers, json={"deadline_reminder_days": 7})
    titles = [it["opportunity"]["title"] for it in _reminders(client, headers)]
    assert titles == ["관심 D-5"]

    # 0(끄기) → 빈 리스트
    client.put("/api/v1/settings/notification", headers=headers, json={"deadline_reminder_days": 0})
    assert _reminders(client, headers) == []


def test_done_past_closed_excluded(client, auth, db_session):
    headers, cid = auth
    done = _seed_opp(db_session, "진행완료 D-1", days=1)
    _pursue(db_session, cid, done, stage="done")        # 완료 → 제외
    past = _seed_opp(db_session, "관심 마감지남", days=-1)
    _save(db_session, cid, past)                          # 마감 경과 → 제외
    closed = _seed_opp(db_session, "관심 마감상태", days=1, status="closed")
    _save(db_session, cid, closed)                        # closed → 제외

    assert _reminders(client, headers) == []


def test_tenant_isolation(client, db_session):
    def _reg(name):
        email = f"rem_{uuid.uuid4().hex[:8]}@example.com"
        r = client.post("/api/v1/auth/register",
                        json={"email": email, "password": "passw0rd!", "company_name": name})
        from app.core.security import decode_access_token  # noqa: PLC0415
        tok = r.json()["access_token"]
        return {"Authorization": f"Bearer {tok}"}, uuid.UUID(decode_access_token(tok)["company_id"])

    ha, ca = _reg("A")
    hb, _ = _reg("B")
    oid = _seed_opp(db_session, "A의 관심 D-1", days=1)
    _save(db_session, ca, oid)

    assert [it["opportunity"]["title"] for it in _reminders(client, ha)] == ["A의 관심 D-1"]
    assert _reminders(client, hb) == []


# ── send_deadline_reminders (Celery, 멱등) ───────────────────────────────────

class _NoCloseSession:
    """공유 트랜잭션 보존 래퍼: close/rollback no-op, commit→flush(브리핑 테스트와 동일)."""

    def __init__(self, session):
        self._s = session

    def __getattr__(self, name):
        return getattr(self._s, name)

    def commit(self):
        self._s.flush()

    def close(self):
        pass

    def rollback(self):
        pass


def _patch_session(db_session):
    return patch(
        "app.services.notifications.tasks.SessionLocal",
        return_value=_NoCloseSession(db_session),
    )


def test_send_deadline_reminders_idempotent(db_session):
    from sqlalchemy import func, select  # noqa: PLC0415

    from app.db.models.accounts import Company, NotificationSetting  # noqa: PLC0415
    from app.db.models.billing import Subscription  # noqa: PLC0415
    from app.db.models.opportunity import UserOpportunityAction  # noqa: PLC0415
    from app.services.notifications.tasks import send_deadline_reminders  # noqa: PLC0415

    cid = uuid.uuid4()
    db_session.add(Company(id=cid, name="리마인드발송", phone="01012345678", onboarding_status="ready"))
    db_session.add(NotificationSetting(company_id=cid, enabled=True))
    db_session.add(Subscription(company_id=cid, plan_code="basic_monthly", status="active"))
    db_session.flush()
    oid = _seed_opp(db_session, "관심 D-1 발송대상", days=1)
    _save(db_session, cid, oid)

    provider = MagicMock()
    with _patch_session(db_session):
        r1 = send_deadline_reminders(_provider=provider)
        r2 = send_deadline_reminders(_provider=provider)

    assert r1 == {"sent": 1, "skipped": 0, "failed": 0}
    assert r2 == {"sent": 0, "skipped": 1, "failed": 0}  # 2회차 멱등 skip
    assert provider.send_sms.call_count == 1            # 발송은 1회만
    assert provider.send_sms.call_args.args[0] == "01012345678"

    n = db_session.scalar(
        select(func.count()).select_from(UserOpportunityAction).where(
            UserOpportunityAction.company_id == cid,
            UserOpportunityAction.action_type == "deadline_reminded",
        )
    )
    assert n == 1  # 멱등 기록 1건
