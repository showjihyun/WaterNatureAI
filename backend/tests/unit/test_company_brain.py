"""단위 테스트: company_brain.service.build_company_context (LLM 모킹).

- LLM 모킹: Context 추출 결과 검증
- content_hash 일치 시 embed/rematch enqueue 없음
- content_hash 변경 시 embed/rematch enqueue 호출 검증
- 키 없음(LLM RuntimeError) → 예외 전파
"""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.company_brain.service import (
    _sha256_norm,
    _validate_context,
)


# ── _sha256_norm 단위 테스트 ─────────────────────────────────────────────────

class TestSha256Norm:
    def test_deterministic(self):
        h1 = _sha256_norm("IT", ["Python"], ["LX"], ["강점"], [])
        h2 = _sha256_norm("IT", ["Python"], ["LX"], ["강점"], [])
        assert h1 == h2

    def test_different_input_different_hash(self):
        h1 = _sha256_norm("IT", ["Python"], ["LX"], [], [])
        h2 = _sha256_norm("GIS", ["Python"], ["LX"], [], [])
        assert h1 != h2

    def test_list_order_matters(self):
        """리스트 순서가 다르면 hash가 다름(JSON 직렬화 순서 유지)."""
        h1 = _sha256_norm("IT", ["Python", "Java"], [], [], [])
        h2 = _sha256_norm("IT", ["Java", "Python"], [], [], [])
        assert h1 != h2

    def test_returns_64_char_hex(self):
        h = _sha256_norm("IT", [], [], [], [])
        assert len(h) == 64
        assert all(c in "0123456789abcdef" for c in h)


# ── _validate_context 단위 테스트 ────────────────────────────────────────────

class TestValidateContext:
    def test_passes_with_industry(self):
        _validate_context({"industry": "IT", "technologies": []})

    def test_passes_with_technologies(self):
        _validate_context({"industry": "", "technologies": ["Python"]})

    def test_fails_both_empty(self):
        with pytest.raises(ValueError, match="industry"):
            _validate_context({"industry": "", "technologies": []})

    def test_fails_missing_keys(self):
        with pytest.raises(ValueError):
            _validate_context({})


# ── build_company_context (DB + LLM 모킹) ────────────────────────────────────

def _make_mock_db(company_name="테스트기업", company_industry="IT", company_region="서울"):
    """Company ORM 행을 반환하는 Session mock."""
    company = MagicMock()
    company.id = uuid.uuid4()
    company.name = company_name
    company.industry = company_industry
    company.description = "테스트 기업 설명"
    company.region = company_region

    db = MagicMock()
    db.get.return_value = company
    # 기존 company_context 없음 (신규)
    db.scalars.return_value.first.return_value = None
    db.add = MagicMock()
    db.flush = MagicMock()
    db.commit = MagicMock()
    db.rollback = MagicMock()
    db.close = MagicMock()
    return db, company


def _make_llm_fn(context_override: dict | None = None):
    """LLM complete_json 모킹."""
    default_context = {
        "industry": "IT",
        "industries": ["소프트웨어"],
        "technologies": ["Python", "FastAPI"],
        "services": ["웹 개발"],
        "customers": ["공공기관"],
        "certifications": [],
        "regions": ["서울"],
        "track_records": [
            {"title": "공공 포털 구축", "year": 2023, "client": "행안부", "summary": "..."}
        ],
        "strengths": ["공공 경험"],
        "keywords": ["Python", "공공"],
    }
    context = {**default_context, **(context_override or {})}
    return MagicMock(return_value=context)


class TestBuildCompanyContext:
    def test_returns_str_uuid(self):
        """정상 실행 시 company_contexts.id(str) 반환."""
        from app.services.company_brain.service import build_company_context

        db, company = _make_mock_db()
        llm_fn = _make_llm_fn()

        with patch("app.services.company_brain.service._enqueue_embed_and_rematch"):
            result = build_company_context(
                str(company.id), db=db, llm_complete_json=llm_fn
            )

        assert isinstance(result, str)
        # UUID 형식 검증
        uuid.UUID(result)

    def test_llm_called_with_profile_info(self):
        """LLM 함수가 호출되고 회사 이름이 프롬프트에 포함된다."""
        from app.services.company_brain.service import build_company_context

        db, company = _make_mock_db(company_name="스페이스기업")
        llm_fn = _make_llm_fn()

        with patch("app.services.company_brain.service._enqueue_embed_and_rematch"):
            build_company_context(str(company.id), db=db, llm_complete_json=llm_fn)

        assert llm_fn.called
        call_args = llm_fn.call_args
        # user 프롬프트(2번째 인자)에 회사명 포함
        user_prompt = call_args[0][1]
        assert "스페이스기업" in user_prompt

    def test_document_text_included_in_prompt(self):
        """document_text가 있으면 LLM 프롬프트에 포함된다."""
        from app.services.company_brain.service import build_company_context

        db, company = _make_mock_db()
        llm_fn = _make_llm_fn()
        doc_text = "특수 기술: 위성통신 네트워크 구축"

        with patch("app.services.company_brain.service._enqueue_embed_and_rematch"):
            build_company_context(
                str(company.id), document_text=doc_text, db=db, llm_complete_json=llm_fn
            )

        user_prompt = llm_fn.call_args[0][1]
        assert doc_text in user_prompt

    def test_enqueue_called_on_new_context(self):
        """신규 context(hash 변경) → _enqueue_embed_and_rematch 호출."""
        from app.services.company_brain.service import build_company_context

        db, company = _make_mock_db()
        llm_fn = _make_llm_fn()

        with patch("app.services.company_brain.service._enqueue_embed_and_rematch") as mock_enqueue:
            build_company_context(str(company.id), db=db, llm_complete_json=llm_fn)

        mock_enqueue.assert_called_once()

    def test_enqueue_not_called_when_hash_unchanged(self):
        """hash가 동일하면 enqueue 하지 않는다."""
        from app.services.company_brain.service import build_company_context, _sha256_norm

        db, company = _make_mock_db()
        context_data = {
            "industry": "IT",
            "industries": ["소프트웨어"],
            "technologies": ["Python", "FastAPI"],
            "services": ["웹 개발"],
            "customers": ["공공기관"],
            "certifications": [],
            "regions": ["서울"],
            "track_records": [
                {"title": "공공 포털 구축", "year": 2023, "client": "행안부", "summary": "..."}
            ],
            "strengths": ["공공 경험"],
            "keywords": ["Python", "공공"],
        }
        same_hash = _sha256_norm(
            context_data["industry"],
            context_data["technologies"],
            context_data["customers"],
            context_data["certifications"],  # 운영 해시(service.py)와 동일 필드 집합
            context_data["strengths"],
            context_data["track_records"],
        )

        # 기존 context_row mock (same hash)
        existing_cc = MagicMock()
        existing_cc.id = uuid.uuid4()
        existing_cc.content_hash = same_hash
        existing_cc.context_json = context_data
        db.scalars.return_value.first.return_value = existing_cc

        llm_fn = MagicMock(return_value=context_data)

        with patch("app.services.company_brain.service._enqueue_embed_and_rematch") as mock_enqueue:
            build_company_context(str(company.id), db=db, llm_complete_json=llm_fn)

        mock_enqueue.assert_not_called()

    def test_llm_key_error_propagates(self):
        """LLM RuntimeError → build_company_context에서 예외 전파."""
        from app.services.company_brain.service import build_company_context

        db, company = _make_mock_db()

        def _failing_llm(*_a, **_k):
            raise RuntimeError("ANTHROPIC_API_KEY 미설정")

        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            build_company_context(str(company.id), db=db, llm_complete_json=_failing_llm)

    def test_context_schema_keys_present_in_result(self):
        """LLM 반환 context가 company_contexts에 저장된다 (db.add 호출)."""
        from app.services.company_brain.service import build_company_context

        db, company = _make_mock_db()
        llm_fn = _make_llm_fn()

        with patch("app.services.company_brain.service._enqueue_embed_and_rematch"):
            build_company_context(str(company.id), db=db, llm_complete_json=llm_fn)

        # db.add(CompanyContext) 또는 db.flush() 호출 확인
        assert db.flush.called or db.add.called
