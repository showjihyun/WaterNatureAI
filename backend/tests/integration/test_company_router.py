"""통합: company 라우터 — 온보딩 흐름(profile→document→brain→ready).

실 PG(alembic 스키마) + TestClient. 외부 실호출 없음:
- LLM off(build_company_context에 llm 주입 안 함 → 프로필 fallback).
- embed/rematch enqueue는 monkeypatch로 모킹·검증.

register로 회사+access token 발급 → Authorization: Bearer 로 호출.
TEST_DATABASE_URL 없으면 skip.
"""
from __future__ import annotations

import os
import uuid
from unittest.mock import MagicMock

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
    """get_session을 공유 트랜잭션(commit→flush)으로 오버라이드한 TestClient."""
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
    """register → (headers, company_id). 회사는 onboarding_status='profile'로 생성됨."""
    email = f"onboard_{uuid.uuid4().hex[:8]}@example.com"
    resp = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "passw0rd!", "company_name": "온보딩테스트기업"},
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    from app.core.security import decode_access_token  # noqa: PLC0415

    company_id = uuid.UUID(decode_access_token(token)["company_id"])
    return {"Authorization": f"Bearer {token}"}, company_id


@pytest.fixture()
def mock_enqueue(monkeypatch):
    """embed_company_context.si / matching.run_daily.si (chain) 모킹(외부 실호출 차단).

    실제 모듈 속성만 monkeypatch(종료 시 원복) — sys.modules에 가짜 모듈을 심지 않아
    다른 통합 테스트(matching) 오염을 방지한다. embedding.tasks는 conftest 스텁 사용.
    """
    import app.services.matching.tasks as matching_tasks  # noqa: PLC0415

    embed = MagicMock(name="embed_company_context")
    run_daily = MagicMock(name="run_daily")

    # conftest가 sys.modules에 넣어둔 embedding.tasks 스텁(embed_opportunity 보유) 위에 추가.
    import app.services.embedding.tasks as embed_tasks  # noqa: PLC0415

    monkeypatch.setattr(embed_tasks, "embed_company_context", embed, raising=False)
    monkeypatch.setattr(matching_tasks, "run_daily", run_daily, raising=False)

    return {"embed": embed, "run_daily": run_daily}


def test_get_profile_returns_current_company(client, auth):
    headers, company_id = auth
    resp = client.get("/api/v1/company/profile", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(company_id)
    assert body["name"] == "온보딩테스트기업"
    assert body["onboarding_status"] == "profile"


def test_put_profile_updates_fields_and_advances_status(client, auth):
    headers, _ = auth
    resp = client.put(
        "/api/v1/company/profile",
        headers=headers,
        json={
            "industry": "공간정보",
            "description": "GIS·디지털트윈 전문",
            "region": "서울",
            "phone": "021112222",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["industry"] == "공간정보"
    assert body["region"] == "서울"
    assert body["phone"] == "021112222"
    # profile → document 전이
    assert body["onboarding_status"] == "document"


def test_put_profile_partial_does_not_overwrite_unset(client, auth):
    headers, _ = auth
    client.put("/api/v1/company/profile", headers=headers, json={"industry": "공간정보"})
    # 두 번째 PUT: phone만 — industry는 유지되어야 함
    resp = client.put("/api/v1/company/profile", headers=headers, json={"phone": "010"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["industry"] == "공간정보"
    assert body["phone"] == "010"


def test_post_brain_creates_context_and_marks_ready(client, auth, mock_enqueue):
    from sqlalchemy import select  # noqa: PLC0415

    from app.db.models.accounts import Company  # noqa: PLC0415
    from app.db.models.company_context import CompanyContext  # noqa: PLC0415

    headers, company_id = auth
    # 프로필 채워 매칭 신호 확보(_validate_context: industry 필요)
    client.put(
        "/api/v1/company/profile",
        headers=headers,
        json={"industry": "공간정보", "description": "GIS 전문", "region": "서울"},
    )

    resp = client.post("/api/v1/company/brain", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["onboarding_status"] == "ready"
    cc_id = body["company_context_id"]
    assert cc_id

    # company_contexts 행 생성 확인
    from app.main import app  # noqa: PLC0415
    from app.db.base import get_session  # noqa: PLC0415

    gen = app.dependency_overrides[get_session]()
    db = next(gen)
    cc = db.scalar(
        select(CompanyContext).where(CompanyContext.company_id == company_id)
    )
    assert cc is not None
    assert str(cc.id) == cc_id
    assert cc.context_json["industry"] == "공간정보"
    assert cc.content_hash is not None

    company = db.get(Company, company_id)
    assert company.onboarding_status == "ready"

    # content_hash 신규 → embed→run_daily chain enqueue 검증(외부 실호출 모킹).
    # 순서 보장 위해 .delay() 2회가 아닌 chain(embed.si → run_daily.si) 사용.
    mock_enqueue["embed"].si.assert_called_once_with(cc_id)
    mock_enqueue["run_daily"].si.assert_called_once()


def _sample_pdf_bytes() -> bytes:
    from pathlib import Path  # noqa: PLC0415

    return (Path(__file__).parent.parent / "fixtures" / "sample_brochure.pdf").read_bytes()


def test_post_documents_parses_and_stores(client, auth):
    """회사소개서 PDF 업로드 → 파싱·저장 + 온보딩 document→brain 전이 (FR-004)."""
    from app.db.base import get_session  # noqa: PLC0415
    from app.db.models.accounts import Company  # noqa: PLC0415
    from app.main import app  # noqa: PLC0415

    headers, company_id = auth
    # 프로필 입력으로 status profile→document 전이(업로드가 document→brain 전이하도록)
    client.put("/api/v1/company/profile", headers=headers, json={"industry": "소프트웨어"})

    resp = client.post(
        "/api/v1/company/documents",
        headers=headers,
        files={"file": ("샘플소개서.pdf", _sample_pdf_bytes(), "application/pdf")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "parsed"
    assert body["filename"] == "샘플소개서.pdf"
    assert body["page_count"] == 1
    assert body["char_count"] > 50
    assert "샘플테크" in body["preview"]

    # DB 저장 확인 + 온보딩 전이
    db = next(app.dependency_overrides[get_session]())
    company = db.get(Company, company_id)
    assert company.document_text and "클라우드" in company.document_text
    assert company.document_filename == "샘플소개서.pdf"
    assert company.onboarding_status == "brain"


def test_post_documents_rejects_non_pdf_extension(client, auth):
    headers, _ = auth
    resp = client.post(
        "/api/v1/company/documents",
        headers=headers,
        files={"file": ("resume.docx", b"PK\x03\x04 docx", "application/octet-stream")},
    )
    assert resp.status_code == 415, resp.text


def test_post_documents_rejects_invalid_pdf(client, auth):
    headers, _ = auth
    resp = client.post(
        "/api/v1/company/documents",
        headers=headers,
        files={"file": ("broken.pdf", b"not a real pdf", "application/pdf")},
    )
    assert resp.status_code == 422, resp.text


def test_llm_settings_key_encrypted_in_db_and_not_leaked(client, auth):
    """설정에서 입력한 LLM 키 → DB에 암호화 저장(평문 미저장)·API 미노출, 공급자 선택.

    PUT /settings/llm 은 시스템 전역 설정이라 **운영자 전용(CurrentAdmin)** 으로 게이팅됨
    → 테스트에선 admin 의존성을 오버라이드해 운영자 경로로 키 암호화 동작을 검증한다.
    """
    from app.api.deps import get_admin_email  # noqa: PLC0415
    from app.core import crypto  # noqa: PLC0415
    from app.db.base import get_session  # noqa: PLC0415
    from app.db.models.app_settings import AppSetting  # noqa: PLC0415
    from app.main import app  # noqa: PLC0415

    headers, _ = auth
    raw_key = "sk-test-SECRET-9f8e7d6c"

    app.dependency_overrides[get_admin_email] = lambda: "admin@bizradar.local"
    try:
        # PUT: openai 선택 + 키 입력 (운영자 흐름)
        resp = client.put(
            "/api/v1/settings/llm",
            headers=headers,
            json={"provider": "openai", "model": "gpt-5.4", "api_key": raw_key},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["provider"] == "openai"
        assert resp.json()["model"] == "gpt-5.4"

        # GET: 활성=openai/gpt-5.4, openai configured=True, 키 원문 미노출
        g = client.get("/api/v1/settings/llm", headers=headers).json()
        assert g["provider"] == "openai" and g["model"] == "gpt-5.4"
        openai_info = next(p for p in g["providers"] if p["provider"] == "openai")
        assert openai_info["configured"] is True
        assert raw_key not in str(g)  # 응답 어디에도 키 원문 없음

        # DB: 평문이 아닌 ciphertext 저장 + 복호화 시 원문 일치
        gen = app.dependency_overrides[get_session]()
        db = next(gen)
        row = db.get(AppSetting, "llm_keys")
        assert row is not None
        ct = row.value["openai"]
        assert ct != raw_key and raw_key not in ct  # 평문 미저장
        assert crypto.decrypt(ct) == raw_key
    finally:
        app.dependency_overrides.pop(get_admin_email, None)


def test_llm_settings_put_forbidden_for_non_admin(client, auth):
    """일반 사용자는 시스템 전역 LLM 설정을 변경할 수 없다(403) — 권한상승 차단 회귀 테스트."""
    headers, _ = auth  # admin_emails 미설정/비운영자 → CurrentAdmin 게이트가 403
    resp = client.put(
        "/api/v1/settings/llm",
        headers=headers,
        json={"provider": "openai", "model": "gpt-5.4", "api_key": "sk-attacker"},
    )
    assert resp.status_code == 403, resp.text


def test_endpoints_require_auth(client):
    # 토큰 미제출 → HTTPBearer(auto_error)가 401 반환(403은 토큰 有·company 스코프 無일 때).
    assert client.get("/api/v1/company/profile").status_code == 401
    assert client.put("/api/v1/company/profile", json={}).status_code == 401
    assert client.post("/api/v1/company/brain").status_code == 401
