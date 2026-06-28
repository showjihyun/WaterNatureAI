"""카카오/SOLAPI 발신 설정 — app_settings('kakao')에 저장(시크릿은 Fernet 암호화).

LLM 키와 동일 패턴(services/llm.py): 설정 UI 입력 → 시크릿은 암호화하여 DB 저장,
미설정 시 .env(config) 폴백. **API 키/시크릿은 클라이언트에 절대 반환하지 않는다**
(설정 여부 bool만). pfId(발신키)·템플릿코드는 자격증명이 아닌 식별자라 평문 저장·표시.

카카오 발신 계정은 플랫폼 전역(1개 SOLAPI 계정)이므로 운영자만 변경한다(라우터에서 게이트).
"""
from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_KEY = "kakao"


def resolve_kakao_config(db=None) -> dict:
    """발송에 쓸 최종 카카오 설정 — DB(암호화) 우선, .env(config) 폴백."""
    cfg = {
        "provider": settings.kakao_provider,
        "sender_key": settings.kakao_sender_key,
        "template_briefing": settings.kakao_template_briefing,
        "api_key": settings.solapi_api_key,
        "api_secret": settings.solapi_api_secret,
        "base_url": settings.solapi_base_url,
    }
    if db is None:
        return cfg
    try:
        from app.core import crypto  # noqa: PLC0415
        from app.db.models.app_settings import AppSetting  # noqa: PLC0415

        row = db.get(AppSetting, _KEY)
        if row and isinstance(row.value, dict):
            v = row.value
            if v.get("provider"):
                cfg["provider"] = v["provider"]
            if v.get("sender_key"):
                cfg["sender_key"] = v["sender_key"]
            if v.get("template_briefing"):
                cfg["template_briefing"] = v["template_briefing"]
            if v.get("api_key_enc"):
                dec = crypto.decrypt(v["api_key_enc"])
                if dec:
                    cfg["api_key"] = dec
            if v.get("api_secret_enc"):
                dec = crypto.decrypt(v["api_secret_enc"])
                if dec:
                    cfg["api_secret"] = dec
    except Exception as exc:  # noqa: BLE001
        logger.debug("kakao config 조회 실패 — .env 폴백: %s", exc)
    return cfg


def set_kakao_config(
    db,
    *,
    provider: str | None = None,
    sender_key: str | None = None,
    template_briefing: str | None = None,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> None:
    """입력값 저장 — 시크릿(api_key/secret)은 **암호화**. 빈 값은 기존 유지(미덮어쓰기)."""
    from app.core import crypto  # noqa: PLC0415
    from app.db.models.app_settings import AppSetting  # noqa: PLC0415

    row = db.get(AppSetting, _KEY)
    val = dict(row.value) if row and isinstance(row.value, dict) else {}

    if provider and provider.strip():
        val["provider"] = provider.strip()
    if sender_key is not None and sender_key.strip():
        val["sender_key"] = sender_key.strip()
    if template_briefing is not None and template_briefing.strip():
        val["template_briefing"] = template_briefing.strip()
    if api_key is not None and api_key.strip():
        val["api_key_enc"] = crypto.encrypt(api_key.strip())
    if api_secret is not None and api_secret.strip():
        val["api_secret_enc"] = crypto.encrypt(api_secret.strip())

    if row is None:
        db.add(AppSetting(key=_KEY, value=val))
    else:
        row.value = val  # JSONB 변경 감지 위해 새 dict 대입
    db.commit()


def kakao_status(db) -> dict:
    """GET용 상태 — 시크릿은 설정 여부(bool)만, 식별자(pfId·템플릿·공급자)는 값 노출."""
    cfg = resolve_kakao_config(db)
    return {
        "provider": cfg["provider"],
        "sender_key": cfg["sender_key"],
        "template_briefing": cfg["template_briefing"],
        "api_key_configured": bool(cfg["api_key"]),
        "api_secret_configured": bool(cfg["api_secret"]),
        "configured": bool(
            cfg["api_key"] and cfg["api_secret"] and cfg["sender_key"] and cfg["template_briefing"]
        ),
    }
