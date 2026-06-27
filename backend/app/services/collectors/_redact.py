"""민감정보 마스킹 — 수집기 예외/URL에 포함된 서비스키를 로그·DB에 남기지 않도록.

data.go.kr·bizinfo API는 서비스키를 **쿼리스트링**으로 전송한다. httpx가 4xx에서
던지는 HTTPStatusError 메시지에는 요청 URL 전체(= serviceKey 값 포함)가 들어가므로,
그 문자열을 DB(error_message)나 로그에 그대로 쓰면 운영 크리덴셜이 유출된다.
"""
from __future__ import annotations

import re

# serviceKey=... / crtfcKey=... / apiKey=... 의 '값'만 마스킹(키 이름은 보존).
_SECRET_QS = re.compile(
    r"((?:serviceKey|crtfcKey|apiKey|api_key|key)=)[^&\s\"'\\]+",
    re.IGNORECASE,
)


def redact_secrets(text: str) -> str:
    """URL 쿼리스트링의 서비스키 값을 '***'로 마스킹한 문자열 반환."""
    return _SECRET_QS.sub(r"\1***", text)
