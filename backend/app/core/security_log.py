"""구조적 보안 이벤트 로깅 (OWASP A09).

인증/권한/남용 이벤트를 일관된 JSON 포맷(`security_event {...}`)으로 전용 'security'
로거에 기록 → 로그 수집·알림(SIEM/Sentry)에서 쿼리·임계 알림이 가능하다.

⚠️ 토큰·비밀번호·API 키 등 **민감값은 절대 기록하지 않는다**(호출측에서 제외).
이메일은 마스킹하여 식별성과 프라이버시를 절충한다.
"""
from __future__ import annotations

import json
import logging
from typing import Any

_logger = logging.getLogger("security")
# 전용 핸들러 — INFO 감사 이벤트까지 항상 stderr(=uvicorn 로그)로 방출되도록 보장
# (앱이 전역 logging을 구성하지 않으면 기본 lastResort는 WARNING+만 출력하므로).
if not _logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s security %(message)s"))
    _logger.addHandler(_handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False  # 루트 전파 차단(중복 출력 방지)


def mask_email(email: str | None) -> str | None:
    """로그용 이메일 마스킹 — 로컬파트 앞 2글자만 노출(예: ad****@x.com)."""
    if not email or "@" not in email:
        return email
    local, _, domain = email.partition("@")
    return f"{local[:2]}{'*' * max(1, len(local) - 2)}@{domain}"


def client_ip(request: Any) -> str | None:
    """클라이언트 IP — 프록시 뒤면 X-Forwarded-For 첫 항목, 아니면 직접 연결 IP."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def log_security_event(
    event: str,
    *,
    actor: str | None = None,
    ip: str | None = None,
    outcome: str | None = None,
    **extra: Any,
) -> None:
    """보안 이벤트를 구조적 JSON으로 기록.

    event: 'login'|'register'|'token_refresh'|'token_reuse_detected'|'logout'|
           'rate_limit_exceeded'|'admin_access'|'admin_config_change' 등.
    actor: 사용자/운영자 이메일(자동 마스킹). outcome: 'success'|'failure'|'blocked'|'denied'|'reuse'.
    extra: 비민감 부가 필드(target/provider/reason 등). None 값은 생략.
    """
    payload: dict[str, Any] = {"event": event}
    if actor is not None:
        payload["actor"] = mask_email(actor) if "@" in actor else actor
    if ip is not None:
        payload["ip"] = ip
    if outcome is not None:
        payload["outcome"] = outcome
    for key, value in extra.items():
        if value is not None:
            payload[key] = value
    level = (
        logging.WARNING
        if outcome in ("failure", "blocked", "denied", "reuse")
        else logging.INFO
    )
    _logger.log(level, "security_event %s", json.dumps(payload, ensure_ascii=False))
