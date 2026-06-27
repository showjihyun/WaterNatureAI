"""통합: 키워드 워치(#5) — 키워드 CRUD + 제목 매칭 피드(미숨김·테넌트 격리).

실 PG(alembic 0009 keyword_watches) + TestClient. TEST_DATABASE_URL 없으면 skip.
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


def _register(client, name="키워드기업"):
    email = f"watch_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": name},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    from app.core.security import decode_access_token  # noqa: PLC0415

    cid = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, cid


@pytest.fixture()
def auth(client):
    return _register(client)


def _seed_opp(db_session, title: str, *, source="narajangter") -> uuid.UUID:
    """워치 피드 후보(open·canonical·미래 마감) opportunity 생성."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    oid = uuid.uuid4()
    db_session.add(
        Opportunity(
            id=oid, source=source, source_uid=f"{source}-{oid}", title=title,
            agency="기관", category="용역", status="open", is_canonical=True,
            deadline=datetime.now(timezone.utc) + timedelta(days=10),
            budget_raw="1억원", budget_amount=100_000_000, raw_json={},
            content_hash=f"h{oid.hex}"[:64].ljust(64, "0"),
        )
    )
    db_session.flush()
    return oid


def _watch_titles(client, headers) -> dict:
    r = client.get("/api/v1/watches/matches", headers=headers)
    assert r.status_code == 200, r.text
    return {it["title"]: it for it in r.json()}


def test_add_list_dedup_delete(client, auth):
    headers, _ = auth
    # 1자 거부
    assert client.post("/api/v1/watches", headers=headers, json={"keyword": "수"}).status_code == 400

    r1 = client.post("/api/v1/watches", headers=headers, json={"keyword": "수처리"})
    assert r1.status_code == 201, r1.text
    wid = r1.json()["id"]

    # 대소문자 무시 중복 멱등(AI/ai)
    client.post("/api/v1/watches", headers=headers, json={"keyword": "AI"})
    dup = client.post("/api/v1/watches", headers=headers, json={"keyword": "ai"})
    assert dup.status_code == 201

    lst = client.get("/api/v1/watches", headers=headers)
    assert lst.status_code == 200
    keywords = [w["keyword"] for w in lst.json()]
    assert keywords == ["수처리", "AI"]  # 등록순, ai 는 중복 미추가

    # 삭제
    assert client.delete(f"/api/v1/watches/{wid}", headers=headers).status_code == 204
    keywords2 = [w["keyword"] for w in client.get("/api/v1/watches", headers=headers).json()]
    assert keywords2 == ["AI"]


def test_matches_by_title_with_matched_keywords(client, auth, db_session):
    headers, _ = auth
    oid_water = _seed_opp(db_session, "스마트 수처리 시스템 구축 사업")
    _seed_opp(db_session, "도로 포장 공사 입찰")
    oid_mem = _seed_opp(db_session, "막여과 공정 R&D 과제")

    # 키워드 없으면 빈 피드
    assert client.get("/api/v1/watches/matches", headers=headers).json() == []

    client.post("/api/v1/watches", headers=headers, json={"keyword": "수처리"})
    matches = _watch_titles(client, headers)
    assert "스마트 수처리 시스템 구축 사업" in matches
    assert "도로 포장 공사 입찰" not in matches
    assert matches["스마트 수처리 시스템 구축 사업"]["matched_keywords"] == ["수처리"]

    # 키워드 추가 → 피드 확장
    client.post("/api/v1/watches", headers=headers, json={"keyword": "막여과"})
    titles = set(_watch_titles(client, headers))
    assert {"스마트 수처리 시스템 구축 사업", "막여과 공정 R&D 과제"} <= titles
    assert oid_water and oid_mem  # 사용


def test_matches_by_agency_and_content(client, auth, db_session):
    """제목엔 없어도 기관·내용(description)에 키워드가 있으면 매칭."""
    from datetime import datetime, timedelta, timezone  # noqa: PLC0415

    from app.db.models.opportunity import Opportunity  # noqa: PLC0415

    headers, _ = auth

    def seed(title: str, agency: str, description: str) -> None:
        oid = uuid.uuid4()
        db_session.add(
            Opportunity(
                id=oid, source="narajangter", source_uid=f"ac-{oid}", title=title,
                agency=agency, category="용역", description=description, status="open",
                is_canonical=True, deadline=datetime.now(timezone.utc) + timedelta(days=10),
                budget_raw="1억원", budget_amount=100_000_000, raw_json={},
                content_hash=f"h{oid.hex}"[:64].ljust(64, "0"),
            )
        )
        db_session.flush()

    seed("도로 포장 공사", "한국수자원공사", "일반 토목 공사")         # 기관에 '수자원'
    seed("스마트 관리 시스템 구축", "조달청", "막여과 기반 정수 처리")  # 내용에 '막여과'
    seed("교량 보수 공사", "국토교통부", "콘크리트 보강")              # 매칭 없음

    client.post("/api/v1/watches", headers=headers, json={"keyword": "수자원"})
    client.post("/api/v1/watches", headers=headers, json={"keyword": "막여과"})

    matches = _watch_titles(client, headers)
    assert "도로 포장 공사" in matches            # 기관 매칭
    assert "스마트 관리 시스템 구축" in matches    # 내용 매칭
    assert "교량 보수 공사" not in matches
    assert matches["도로 포장 공사"]["matched_keywords"] == ["수자원"]
    assert matches["스마트 관리 시스템 구축"]["matched_keywords"] == ["막여과"]


def test_synonym_matching(client, auth, db_session):
    """동의어: 'AI' 워치가 '인공지능' 표현 공고도 매칭(matched_keywords엔 등록 키워드)."""
    headers, _ = auth
    _seed_opp(db_session, "인공지능 학습데이터 구축 사업")  # 제목에 인공지능(AI 동의어)
    _seed_opp(db_session, "도로 포장 공사 입찰")           # 매칭 없음
    client.post("/api/v1/watches", headers=headers, json={"keyword": "AI"})

    matches = _watch_titles(client, headers)
    assert "인공지능 학습데이터 구축 사업" in matches
    assert "도로 포장 공사 입찰" not in matches
    assert matches["인공지능 학습데이터 구축 사업"]["matched_keywords"] == ["AI"]


def test_matches_excludes_hidden(client, auth, db_session):
    headers, cid = auth
    oid = _seed_opp(db_session, "AI 데이터 구축 수처리 통합 사업")
    client.post("/api/v1/watches", headers=headers, json={"keyword": "수처리"})
    assert "AI 데이터 구축 수처리 통합 사업" in _watch_titles(client, headers)

    # 관심없음(hidden) → 피드에서 제외
    r = client.post(f"/api/v1/opportunities/{oid}/hide", headers=headers, json={"reason": "etc"})
    assert r.status_code == 201, r.text
    assert "AI 데이터 구축 수처리 통합 사업" not in _watch_titles(client, headers)


def test_tenant_isolation(client, db_session):
    headers_a, _ = _register(client, "A기업")
    headers_b, _ = _register(client, "B기업")
    _seed_opp(db_session, "수처리 플랜트 유지보수")

    client.post("/api/v1/watches", headers=headers_a, json={"keyword": "수처리"})

    # B는 A의 키워드/피드를 보지 못함
    assert client.get("/api/v1/watches", headers=headers_b).json() == []
    assert client.get("/api/v1/watches/matches", headers=headers_b).json() == []
    # A는 본다
    assert "수처리 플랜트 유지보수" in _watch_titles(client, headers_a)
