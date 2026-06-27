"""LLM 클라이언트 — 멀티 공급자(Anthropic / OpenAI / Gemini) 구조화 출력 래퍼.

- 공급자별 구조화 출력: Anthropic tool_use · OpenAI function calling · Gemini JSON.
- 런타임 공급자/모델은 `app_settings('llm')` → 없으면 config 기본값.
- API 키는 .env(config)에만 보관(설정 UI는 공급자/모델만 선택, 키 입력 없음).
- 키 없으면 호출 시 RuntimeError(score_match가 흡수 → 규칙 폴백).

함수:
  complete_json(system, user, schema, *, provider=None, model=None) -> dict
    provider/model 미지정 시 **config 기본값**(DB 미조회 — 단위테스트 안전).
  resolve_llm_fn(db) -> Callable | None
    DB의 활성 공급자에 키가 있으면 complete_json 클로저, 없으면 None.
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── UI 노출용: 공급자별 선택 가능 모델(첫 항목 = 추천 기본). ──────────────────
PROVIDER_MODELS: dict[str, list[dict]] = {
    "anthropic": [
        {"id": "claude-opus-4-8",   "label": "Claude Opus 4.8 — 최고품질($5/$25)"},
        {"id": "claude-sonnet-4-6", "label": "Claude Sonnet 4.6 — 균형($3/$15)"},
        {"id": "claude-haiku-4-5",  "label": "Claude Haiku 4.5 — 경량·저가($1/$5)"},
    ],
    "openai": [
        {"id": "gpt-5.4",    "label": "GPT-5.4 — 최신"},
        {"id": "gpt-5",      "label": "GPT-5"},
        {"id": "gpt-5-mini", "label": "GPT-5 mini — 경량"},
        {"id": "gpt-4o",     "label": "GPT-4o"},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini — 경량"},
    ],
    "gemini": [
        {"id": "gemini-3.5-flash", "label": "Gemini 3.5 Flash — 최신·경량"},
        {"id": "gemini-2.5-pro",   "label": "Gemini 2.5 Pro"},
        {"id": "gemini-2.5-flash", "label": "Gemini 2.5 Flash — 경량"},
        {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash — 경량"},
    ],
}
PROVIDERS: list[str] = list(PROVIDER_MODELS.keys())

_ENV_VAR = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


# ── 공급자 키/모델 해석 (config) ──────────────────────────────────────────────

def _env_provider_key(provider: str) -> str:
    return {
        "anthropic": settings.anthropic_api_key,
        "openai": settings.openai_api_key,
        "gemini": settings.gemini_api_key,
    }.get(provider, "")


def provider_key_from_db(provider: str, db) -> str | None:
    """DB(app_settings 'llm_keys')에 암호화 저장된 키 복호화. 없으면 None."""
    try:
        from app.core import crypto  # noqa: PLC0415
        from app.db.models.app_settings import AppSetting  # noqa: PLC0415

        row = db.get(AppSetting, "llm_keys")
        if row and isinstance(row.value, dict):
            ct = row.value.get(provider)
            if ct:
                return crypto.decrypt(ct)
    except Exception as exc:  # noqa: BLE001
        logger.debug("llm_keys 복호화 실패(%s): %s", provider, exc)
    return None


def set_provider_key(db, provider: str, raw_key: str) -> None:
    """공급자 API 키를 **암호화**하여 DB(app_settings 'llm_keys')에 저장(평문 미저장)."""
    from app.core import crypto  # noqa: PLC0415
    from app.db.models.app_settings import AppSetting  # noqa: PLC0415

    enc = crypto.encrypt(raw_key)
    row = db.get(AppSetting, "llm_keys")
    if row is None:
        db.add(AppSetting(key="llm_keys", value={provider: enc}))
    else:
        new_val = dict(row.value or {})  # JSONB 변경 감지 위해 새 dict
        new_val[provider] = enc
        row.value = new_val
    db.commit()


def provider_api_key(provider: str, db=None) -> str:
    """공급자 API 키 — **DB(설정 UI, 암호화) 우선**, 없으면 .env(config) 폴백."""
    if db is not None:
        k = provider_key_from_db(provider, db)
        if k:
            return k
    return _env_provider_key(provider)


def provider_default_model(provider: str) -> str:
    return {
        "anthropic": settings.llm_model,
        "openai": settings.openai_model,
        "gemini": settings.gemini_model,
    }.get(provider, "")


def is_provider_configured(provider: str, db=None) -> bool:
    """해당 공급자의 API 키가 설정(DB 또는 .env)돼 있는가."""
    return bool(provider_api_key(provider, db))


def get_active_provider_model(db=None) -> tuple[str, str]:
    """활성 (provider, model). app_settings('llm') 우선, 없으면 config 기본.

    DB 조회 실패(미연결 등)는 흡수하고 config 기본으로 폴백한다.
    """
    provider = settings.llm_provider
    model = provider_default_model(provider)
    try:
        from app.db.base import SessionLocal  # noqa: PLC0415
        from app.db.models.app_settings import AppSetting  # noqa: PLC0415

        own = db is None
        _db = db if db is not None else SessionLocal()
        try:
            row = _db.get(AppSetting, "llm")
            if row and isinstance(row.value, dict):
                provider = row.value.get("provider") or provider
                model = row.value.get("model") or provider_default_model(provider)
        finally:
            if own:
                _db.close()
    except Exception as exc:  # noqa: BLE001
        logger.debug("app_settings('llm') 조회 실패 — config 기본 사용: %s", exc)
    return provider, model


# ── JSON Schema 변환 ({field: type_hint} → JSON Schema) ───────────────────────

def _to_json_schema(schema: dict) -> dict:
    """{field: 'type'} 단순 dict → JSON Schema object. 이미 JSON Schema면 그대로."""
    if schema.get("type") == "object" and "properties" in schema:
        return schema
    properties: dict = {}
    for key, type_hint in schema.items():
        if isinstance(type_hint, str):
            if type_hint in ("str", "string"):
                properties[key] = {"type": "string"}
            elif type_hint.startswith("list"):
                properties[key] = {"type": "array", "items": {"type": "string"}}
            elif type_hint in ("int", "integer", "number", "float"):
                properties[key] = {"type": "number"}
            elif type_hint in ("bool", "boolean"):
                properties[key] = {"type": "boolean"}
            else:
                properties[key] = {"type": "string"}
        else:
            properties[key] = {"type": "object"}
    return {"type": "object", "properties": properties}


# ── 공급자별 구조화 출력 구현 ────────────────────────────────────────────────

def _client(key: str):
    """Anthropic 클라이언트(테스트에서 patch). SDK는 호출 시점에만 import."""
    import anthropic  # noqa: PLC0415

    return anthropic.Anthropic(api_key=key)


def _anthropic_json(system: str, user: str, json_schema: dict, model: str, key: str) -> dict:
    """Anthropic tool_use 강제로 구조화 JSON 반환."""
    client = _client(key)
    tool = {
        "name": "structured_output",
        "description": "구조화된 JSON 출력 도구. 항상 이 도구로 결과를 반환하라.",
        "input_schema": json_schema,
    }
    resp = client.messages.create(
        model=model,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user}],
        tools=[tool],
        tool_choice={"type": "tool", "name": "structured_output"},
    )
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return dict(block.input)
    for block in resp.content:
        if hasattr(block, "text"):
            try:
                return json.loads(block.text)
            except (json.JSONDecodeError, TypeError):
                pass
    raise ValueError("anthropic 응답에 tool_use 블록이 없음")


def _openai_json(system: str, user: str, json_schema: dict, model: str, key: str) -> dict:
    """OpenAI function calling 강제로 구조화 JSON 반환."""
    from openai import OpenAI  # noqa: PLC0415

    client = OpenAI(api_key=key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        tools=[{
            "type": "function",
            "function": {
                "name": "structured_output",
                "description": "구조화된 JSON 출력. 항상 이 함수로 결과를 반환하라.",
                "parameters": json_schema,
            },
        }],
        tool_choice={"type": "function", "function": {"name": "structured_output"}},
    )
    msg = resp.choices[0].message
    for call in (msg.tool_calls or []):
        fn = getattr(call, "function", None)
        if fn is not None and getattr(fn, "arguments", None):
            return json.loads(fn.arguments)
    if msg.content:
        return json.loads(msg.content)
    raise ValueError("openai 응답에 tool_call이 없음")


def _gemini_json(system: str, user: str, json_schema: dict, model: str, key: str) -> dict:
    """Gemini JSON 모드(response_mime_type=application/json)로 구조화 JSON 반환."""
    import google.generativeai as genai  # noqa: PLC0415

    genai.configure(api_key=key)
    gmodel = genai.GenerativeModel(model_name=model, system_instruction=system)
    prompt = (
        f"{user}\n\n반드시 아래 JSON 스키마에 맞는 JSON만 출력하라"
        f"(코드펜스·설명 금지):\n{json.dumps(json_schema, ensure_ascii=False)}"
    )
    resp = gmodel.generate_content(
        prompt,
        generation_config={"response_mime_type": "application/json"},
    )
    return json.loads(resp.text)


_DISPATCH: dict[str, Callable[..., dict]] = {
    "anthropic": _anthropic_json,
    "openai": _openai_json,
    "gemini": _gemini_json,
}


# ── 검증 ──────────────────────────────────────────────────────────────────────

def _validate(result: dict, schema: dict) -> bool:
    """최소 검증: 스키마 키 절반 이상이 결과에 존재."""
    if not isinstance(result, dict):
        return False
    required = list(schema["properties"].keys()) if "properties" in schema else list(schema.keys())
    present = sum(1 for k in required if k in result)
    return present >= max(1, len(required) // 2)


# ── 공개 API ──────────────────────────────────────────────────────────────────

def complete_json(
    system: str, user: str, schema: dict, *,
    provider: str | None = None, model: str | None = None, key: str | None = None,
) -> dict:
    """활성(또는 지정) 공급자로 구조화 JSON을 반환한다.

    provider/model 미지정 시 **config 기본값**을 사용한다(DB 미조회).
    key 미지정 시 .env(config)에서 해석한다. 런타임 DB 키/선택은 resolve_llm_fn(db)가
    provider/model/key를 주입한다.

    Raises:
        RuntimeError: API 키 미설정, 알 수 없는 공급자, 또는 재시도 후 스키마 불일치.
    """
    if provider is None:
        provider = settings.llm_provider
    if model is None:
        model = provider_default_model(provider)

    fn = _DISPATCH.get(provider)
    if fn is None:
        raise RuntimeError(f"알 수 없는 LLM 공급자: {provider} (지원: {', '.join(PROVIDERS)})")

    if key is None:
        key = provider_api_key(provider)
    if not key:
        env = _ENV_VAR.get(provider, "API_KEY")
        raise RuntimeError(f"{env} 미설정 — {provider} 키를 설정 UI 또는 .env에 등록 필요")

    json_schema = _to_json_schema(schema)

    # 1차 시도
    try:
        result = fn(system, user, json_schema, model, key)
        if _validate(result, schema):
            return result
        logger.warning("LLM 출력 스키마 불일치(%s/%s) — 재시도", provider, model)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM 호출 실패(%s/%s, 1차): %s — 재시도", provider, model, exc)

    # 1회 재시도(명시적 지시 추가)
    retry_user = user + "\n\n[재시도] 반드시 스키마에 맞는 JSON만 반환하라."
    result = fn(system, retry_user, json_schema, model, key)
    if not _validate(result, schema):
        raise RuntimeError(
            f"LLM 출력이 스키마를 충족하지 못함({provider}/{model}): keys={list(result.keys())}"
        )
    return result


def resolve_llm_fn(db=None) -> Callable | None:
    """DB의 활성 공급자에 키가 있으면 complete_json 클로저, 없으면 None(규칙 폴백).

    run_daily 등에서 1회 호출해 (provider, model)을 고정한 함수를 얻는다 —
    매 호출마다 DB를 조회하지 않는다.
    """
    provider, model = get_active_provider_model(db)
    key = provider_api_key(provider, db)  # DB(암호화) 우선, .env 폴백
    if not key:
        return None

    def _fn(system: str, user: str, schema: dict) -> dict:
        return complete_json(system, user, schema, provider=provider, model=model, key=key)

    return _fn
