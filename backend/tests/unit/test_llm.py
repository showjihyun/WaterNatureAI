"""단위 테스트: app.services.llm (Anthropic SDK 모킹 — 키 불필요).

- complete_json 파라미터/tool_use 강제 검증
- 스키마 검증 실패 시 재시도 후 RuntimeError
- 키 없음 → RuntimeError (즉시)
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

# ── 모듈 임포트 전 anthropic stub ────────────────────────────────────────────
# anthropic SDK가 미설치 환경에서도 테스트 가능하도록 사전 stub.
import sys
import types as _types

if "anthropic" not in sys.modules:
    _stub = _types.ModuleType("anthropic")
    _stub.Anthropic = MagicMock  # type: ignore[attr-defined]
    sys.modules["anthropic"] = _stub

import app.services.llm as llm_mod


# ── 가짜 Anthropic 응답 생성 헬퍼 ────────────────────────────────────────────

def _make_tool_response(payload: dict) -> MagicMock:
    """tool_use 블록 하나를 가진 Messages.create() 응답 MagicMock."""
    block = SimpleNamespace(type="tool_use", input=payload)
    resp = MagicMock()
    resp.content = [block]
    return resp


def _make_client(payload: dict) -> MagicMock:
    """messages.create() 가 payload를 담은 tool_use 응답을 반환하는 가짜 client."""
    client = MagicMock()
    client.messages.create.return_value = _make_tool_response(payload)
    return client


# ── 테스트 ────────────────────────────────────────────────────────────────────

class TestCompleteJson:
    def test_returns_tool_use_payload(self, monkeypatch):
        """정상 경로: tool_use 블록의 input이 그대로 반환된다."""
        payload = {"industry": "GIS", "technologies": ["디지털트윈"]}
        fake_client = _make_client(payload)
        monkeypatch.setattr(llm_mod.settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(llm_mod.settings, "llm_model", "claude-opus-4-8")

        with patch.object(llm_mod, "_client", return_value=fake_client):
            result = llm_mod.complete_json("system", "user", {"industry": "str"})

        assert result["industry"] == "GIS"
        assert result["technologies"] == ["디지털트윈"]

    def test_passes_tool_choice_and_model(self, monkeypatch):
        """tool_choice=tool, 모델명이 SDK에 정확히 전달된다."""
        payload = {"industry": "IT", "technologies": ["Python"]}
        fake_client = _make_client(payload)
        monkeypatch.setattr(llm_mod.settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(llm_mod.settings, "llm_model", "claude-opus-4-8")

        with patch.object(llm_mod, "_client", return_value=fake_client):
            llm_mod.complete_json("sys", "usr", {"industry": "str", "technologies": "list[str]"})

        call_kwargs = fake_client.messages.create.call_args[1]
        assert call_kwargs["model"] == "claude-opus-4-8"
        assert call_kwargs["tool_choice"]["type"] == "tool"
        assert call_kwargs["tool_choice"]["name"] == "structured_output"
        assert len(call_kwargs["tools"]) == 1
        assert call_kwargs["tools"][0]["name"] == "structured_output"

    def test_retry_on_schema_mismatch(self, monkeypatch):
        """1차 응답이 스키마 불일치 → 재시도 → 성공."""
        call_count = {"n": 0}
        monkeypatch.setattr(llm_mod.settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(llm_mod.settings, "llm_model", "claude-opus-4-8")

        def _create(**kwargs):  # noqa: ARG001
            call_count["n"] += 1
            if call_count["n"] == 1:
                # 1차: 빈 dict (스키마 불일치)
                return _make_tool_response({})
            # 2차: 정상
            return _make_tool_response({"industry": "Fin", "technologies": ["Java"]})

        fake_client = MagicMock()
        fake_client.messages.create.side_effect = _create

        with patch.object(llm_mod, "_client", return_value=fake_client):
            result = llm_mod.complete_json("s", "u", {"industry": "str", "technologies": "list[str]"})

        assert result["industry"] == "Fin"
        assert call_count["n"] == 2

    def test_retry_exhausted_raises_runtime_error(self, monkeypatch):
        """1차 + 재시도 모두 스키마 불일치 → RuntimeError."""
        monkeypatch.setattr(llm_mod.settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(llm_mod.settings, "llm_model", "claude-opus-4-8")

        fake_client = MagicMock()
        # 항상 빈 dict 반환 → 스키마 검증 실패
        fake_client.messages.create.return_value = _make_tool_response({})

        with patch.object(llm_mod, "_client", return_value=fake_client):
            with pytest.raises(RuntimeError, match="스키마"):
                llm_mod.complete_json("s", "u", {"industry": "str", "technologies": "list[str]"})

    def test_missing_key_raises_runtime_error(self, monkeypatch):
        """ANTHROPIC_API_KEY 없으면 즉시 RuntimeError (SDK 호출 전)."""
        monkeypatch.setattr(llm_mod.settings, "anthropic_api_key", "")

        with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
            llm_mod.complete_json("s", "u", {"industry": "str"})

    def test_json_schema_passthrough(self, monkeypatch):
        """schema가 이미 JSON Schema 형식이면 그대로 tool input_schema에 전달."""
        json_schema = {
            "type": "object",
            "properties": {
                "score": {"type": "number"},
                "reasons": {"type": "array", "items": {"type": "string"}},
            },
        }
        payload = {"score": 85, "reasons": ["기술 일치"]}
        fake_client = _make_client(payload)
        monkeypatch.setattr(llm_mod.settings, "anthropic_api_key", "test-key")
        monkeypatch.setattr(llm_mod.settings, "llm_model", "claude-opus-4-8")

        with patch.object(llm_mod, "_client", return_value=fake_client):
            result = llm_mod.complete_json("s", "u", json_schema)

        # tool input_schema = json_schema 그대로
        call_kwargs = fake_client.messages.create.call_args[1]
        assert call_kwargs["tools"][0]["input_schema"] == json_schema
        assert result["score"] == 85


_NUM_SCHEMA = {"type": "object", "properties": {"score": {"type": "number"},
                                                "reasons": {"type": "array",
                                                            "items": {"type": "string"}}}}


class TestMultiProvider:
    def test_openai_dispatch(self, monkeypatch):
        """provider='openai' → OpenAI function calling 경로로 라우팅."""
        monkeypatch.setattr(llm_mod.settings, "openai_api_key", "k")
        fake = MagicMock()
        fn_call = SimpleNamespace(function=SimpleNamespace(arguments='{"score": 80, "reasons": ["x"]}'))
        fake.chat.completions.create.return_value = SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(tool_calls=[fn_call], content=None))]
        )
        with patch("openai.OpenAI", return_value=fake):
            result = llm_mod.complete_json("s", "u", _NUM_SCHEMA, provider="openai", model="gpt-5")
        assert result["score"] == 80
        assert fake.chat.completions.create.call_args[1]["model"] == "gpt-5"

    def test_gemini_dispatch(self, monkeypatch):
        """provider='gemini' → JSON 모드 경로로 라우팅."""
        monkeypatch.setattr(llm_mod.settings, "gemini_api_key", "k")
        gm = MagicMock()
        gm.generate_content.return_value = SimpleNamespace(text='{"score": 77, "reasons": ["y"]}')
        with patch("google.generativeai.GenerativeModel", return_value=gm), \
             patch("google.generativeai.configure"):
            result = llm_mod.complete_json("s", "u", _NUM_SCHEMA, provider="gemini",
                                           model="gemini-2.5-pro")
        assert result["score"] == 77

    def test_unknown_provider_raises(self, monkeypatch):
        with pytest.raises(RuntimeError, match="공급자"):
            llm_mod.complete_json("s", "u", _NUM_SCHEMA, provider="grok", model="x")

    def test_openai_missing_key_raises(self, monkeypatch):
        monkeypatch.setattr(llm_mod.settings, "openai_api_key", "")
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            llm_mod.complete_json("s", "u", _NUM_SCHEMA, provider="openai", model="gpt-5")

    def test_resolve_llm_fn_none_without_key(self, monkeypatch):
        """활성 공급자에 키가 없으면 resolve_llm_fn → None(규칙 폴백)."""
        monkeypatch.setattr(llm_mod, "get_active_provider_model",
                            lambda db=None: ("anthropic", "claude-opus-4-8"))
        monkeypatch.setattr(llm_mod.settings, "anthropic_api_key", "")
        assert llm_mod.resolve_llm_fn(db=None) is None

    def test_resolve_llm_fn_returns_callable_with_key(self, monkeypatch):
        monkeypatch.setattr(llm_mod, "get_active_provider_model",
                            lambda db=None: ("openai", "gpt-5"))
        monkeypatch.setattr(llm_mod.settings, "openai_api_key", "k")
        fn = llm_mod.resolve_llm_fn(db=None)
        assert callable(fn)
