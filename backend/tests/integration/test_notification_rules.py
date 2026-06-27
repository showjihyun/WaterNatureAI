"""통합: 맞춤 알림 규칙(#4) — 적합도 임계값·출처 선택이 브리핑 미리보기에 반영.

실 PG(alembic 0008 min_score/excluded_sources) + TestClient. TEST_DATABASE_URL 없으면 skip.
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
    email = f"rules_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "알림규칙기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    from app.core.security import decode_access_token  # noqa: PLC0415

    cid = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, cid


def _seed_match(db_session, company_id, *, source: str, score: int, with_deadline: bool) -> uuid.UUID:
    """추천(브리핑)에 뜨도록 open·canonical opportunity + match 생성."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.db.models.opportunity import Match, Opportunity  # noqa: PLC0415

    oid = uuid.uuid4()
    db_session.add(
        Opportunity(
            id=oid, source=source, source_uid=f"{source}-{oid}", title=f"{source} 공고",
            agency="기관", category="용역", status="open", is_canonical=True,
            deadline=(datetime.now(timezone.utc) + timedelta(days=10)) if with_deadline else None,
            budget_raw="1억원", budget_amount=100_000_000, raw_json={},
            content_hash=f"h{oid.hex}"[:64].ljust(64, "0"),
        )
    )
    db_session.flush()
    db_session.add(Match(id=uuid.uuid4(), company_id=company_id, opportunity_id=oid, score=score))
    db_session.flush()
    return oid


def _preview(client, headers) -> dict:
    r = client.get("/api/v1/settings/notification/preview", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _put(client, headers, body) -> dict:
    r = client.put("/api/v1/settings/notification", headers=headers, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_min_score_and_source_rules_filter_preview(client, auth, db_session):
    headers, cid = auth
    # narajangter score 70(고적합) / ntis score 52(저적합·마감없음)
    _seed_match(db_session, cid, source="narajangter", score=70, with_deadline=True)
    _seed_match(db_session, cid, source="ntis", score=52, with_deadline=False)

    # 기본(규칙 없음): 둘 다 노출(threshold 35)
    base = _preview(client, headers)
    assert base["count"] == 2
    assert base["min_score"] is None and base["excluded_sources"] == []

    # 적합도 60 이상 → ntis(52) 제외, narajangter(70)만
    _put(client, headers, {"min_score": 60})
    after_score = _preview(client, headers)
    assert after_score["count"] == 1
    assert after_score["min_score"] == 60
    assert {it["source"] for it in after_score["items"]} == {"narajangter"}

    # 임계값 해제 + ntis 출처 제외 → narajangter만
    _put(client, headers, {"min_score": None, "excluded_sources": ["ntis"]})
    after_src = _preview(client, headers)
    assert after_src["count"] == 1
    assert after_src["min_score"] is None and after_src["excluded_sources"] == ["ntis"]
    assert {it["source"] for it in after_src["items"]} == {"narajangter"}

    # 출처 제외 해제 → 다시 둘 다
    _put(client, headers, {"excluded_sources": []})
    restored = _preview(client, headers)
    assert restored["count"] == 2


def test_get_notification_exposes_available_sources(client, auth):
    headers, _ = auth
    r = client.get("/api/v1/settings/notification", headers=headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # 운영 활성 수집기 = 켜고/끌 수 있는 출처
    assert set(body["available_sources"]) >= {"narajangter", "kstartup", "ntis"}
    assert body["min_score"] is None and body["excluded_sources"] == []


def test_unknown_source_rejected(client, auth):
    headers, _ = auth
    r = client.put(
        "/api/v1/settings/notification", headers=headers, json={"excluded_sources": ["bogus"]}
    )
    assert r.status_code == 400, r.text


def test_briefing_includes_keyword_matches(client, auth, db_session):
    """브리핑 미리보기 = AI 매칭 + 키워드 매칭(점수 없어도 포함, matched_keywords)."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    headers, cid = auth
    _seed_match(db_session, cid, source="narajangter", score=70, with_deadline=True)  # AI 매칭
    # 키워드 매칭(AI 매칭 없음) opp — 제목에 '수처리'
    oid = uuid.uuid4()
    db_session.add(
        Opportunity(
            id=oid, source="kstartup", source_uid=f"kw-{oid}", title="스마트 수처리 시스템 구축",
            agency="기관", category="용역", status="open", is_canonical=True,
            deadline=datetime.now(timezone.utc) + timedelta(days=10),
            budget_raw="1억원", budget_amount=100_000_000, raw_json={},
            content_hash=f"h{oid.hex}"[:64].ljust(64, "0"),
        )
    )
    db_session.flush()
    client.post("/api/v1/watches", headers=headers, json={"keyword": "수처리"})

    items = {it["title"]: it for it in _preview(client, headers)["items"]}
    assert "스마트 수처리 시스템 구축" in items            # 키워드 매칭 포함
    assert items["스마트 수처리 시스템 구축"]["score"] is None  # AI 점수 없음
    assert items["스마트 수처리 시스템 구축"]["matched_keywords"] == ["수처리"]
    assert "narajangter 공고" in items                     # AI 매칭도 그대로


def test_briefing_excludes_hidden(client, auth, db_session):
    """브리핑도 hidden(관심없음) 공고 제외(#3 일관)."""
    headers, cid = auth
    oid = _seed_match(db_session, cid, source="narajangter", score=70, with_deadline=True)
    assert "narajangter 공고" in {it["title"] for it in _preview(client, headers)["items"]}

    r = client.post(f"/api/v1/opportunities/{oid}/hide", headers=headers, json={"reason": "etc"})
    assert r.status_code == 201, r.text
    assert "narajangter 공고" not in {it["title"] for it in _preview(client, headers)["items"]}
