"""LLM provider smoke 테스트 (실 Anthropic API 호출).

ANTHROPIC_API_KEY(.env) 있으면 실 호출, 없으면 skip.
1건만 호출해 complete_json 응답 형식을 검증.

실행:
    backend/.env 에 ANTHROPIC_API_KEY=... 설정 후
    pytest tests/smoke/test_llm_live.py -v
"""
from __future__ import annotations

import pytest

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    not settings.anthropic_api_key,
    reason="ANTHROPIC_API_KEY not set (.env) — LLM smoke skipped",
)


def test_complete_json_live() -> None:
    """실 Anthropic API 호출 → structured_output 형식 검증."""
    from app.services.llm import complete_json

    schema = {
        "type": "object",
        "properties": {
            "industry": {"type": "string"},
            "technologies": {"type": "array", "items": {"type": "string"}},
        },
    }
    result = complete_json(
        system="간단한 기업 분석 테스트. 항상 structured_output 도구를 사용하라.",
        user="회사: 서울소프트웨어\n업종: 소프트웨어 개발\n기술: Python, FastAPI",
        schema=schema,
    )

    assert isinstance(result, dict)
    assert "industry" in result or "technologies" in result
