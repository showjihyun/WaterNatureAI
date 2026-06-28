"""인증 엔드포인트 레이트리밋 — Redis 고정창 카운터(분산 워커 공유).

보안: 무차별 대입/크리덴셜 스터핑/이메일 열거를 완화. 운영(APP_ENV!=local)에서만
활성화하여 로컬 개발·테스트 흐름에는 영향을 주지 않는다. Redis 장애 시 fail-open
(가용성 우선) — 카운팅이 불가능해도 인증 자체를 막지는 않는다.
"""
from __future__ import annotations

import logging
from collections.abc import Callable

import redis
from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.core.security_log import log_security_event

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _redis() -> redis.Redis:
    """지연 생성 싱글턴 — import 시 Redis 연결을 강제하지 않음."""
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, socket_timeout=0.25)
    return _client


def rate_limit(name: str, *, limit: int, window_sec: int) -> Callable[[Request], None]:
    """IP 기준 고정창 레이트리밋 FastAPI 의존성 생성.

    name: 카운터 네임스페이스(엔드포인트별 분리). limit: 창당 허용 횟수. window_sec: 창 길이.
    """

    def _dep(request: Request) -> None:
        if settings.app_env == "local":
            return  # 로컬/테스트 비활성(운영에서만 적용)
        ip = request.client.host if request.client else "unknown"
        key = f"rl:{name}:{ip}"
        try:
            count = _redis().incr(key)
            if count == 1:
                _redis().expire(key, window_sec)
        except Exception as exc:  # noqa: BLE001 — Redis 장애 시 인증 차단 금지(fail-open)
            logger.warning("rate_limit redis 오류(fail-open): %s", exc)
            return
        if count > limit:
            log_security_event("rate_limit_exceeded", ip=ip, outcome="blocked", name=name)
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "요청이 너무 많습니다. 잠시 후 다시 시도하세요.",
            )

    return _dep
