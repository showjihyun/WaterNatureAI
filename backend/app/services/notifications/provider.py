"""알림 발송 제공자 추상화 — 카카오 알림톡 + SMS 폴백.

정본: docs/04-architecture/daily-briefing.md §2·§5, blocker-resolution.md §1.
MVP 중계사 = SOLAPI(1순위), 확장 시 NHN Cloud. ⚠️ 발신프로필·템플릿 심사·사업자등록 선행.

🚧 키 미주입(사업자 확보 전) = RuntimeError. 실키 주입 시 live 동작하도록 격리.
인증: SOLAPI HMAC-SHA256 — Authorization 헤더에 apiKey/date/salt/signature.
외부 HTTP는 httpx.Client(테스트는 MockTransport로 모킹, 실호출 금지).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# SOLAPI 메시지 발송 엔드포인트(공식 v4). 경로/필드는 사업자 후 실연동에서 최종 확정.
_SEND_PATH = "/messages/v4/send"

# 알림톡 미등록/차단 → SMS 폴백 트리거로 매핑할 SOLAPI 실패 상태/사유 코드.
#   발신프로필 미등록·템플릿 불일치·수신거부 등은 재시도 무의미 → 폴백.
# 출처: SOLAPI 메시지 상태/사유 코드표(실연동 시 최종 대조).
_FALLBACK_STATUS_CODES: frozenset[str] = frozenset(
    {
        "3008",  # 발신프로필 미등록/차단류
        "3013",  # 템플릿 미승인/불일치
        "3014",  # 수신거부
        "ATR0",  # 알림톡 일반 실패(친구 아님/차단 등)
    }
)


@dataclass
class SendResult:
    provider_msg_id: str
    channel: str


class NotRegisteredOrBlocked(RuntimeError):
    """알림톡 미등록/차단 → SMS 폴백 트리거."""


class NotificationProvider(ABC):
    @abstractmethod
    def send_alimtalk(self, phone: str, template_code: str, variables: dict) -> SendResult: ...

    @abstractmethod
    def send_sms(self, phone: str, text: str) -> SendResult: ...


def _hmac_auth_header(api_key: str, api_secret: str) -> str:
    """SOLAPI HMAC-SHA256 Authorization 헤더 생성.

    형식: ``HMAC-SHA256 apiKey={key}, date={ISO8601}, salt={salt}, signature={sig}``
    signature = HMAC_SHA256(secret, date + salt) 의 hexdigest.
    ⚠️ secret 은 로그에 남기지 않는다.
    """
    date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    salt = secrets.token_hex(16)
    signature = hmac.new(
        api_secret.encode("utf-8"),
        (date + salt).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return (
        f"HMAC-SHA256 apiKey={api_key}, date={date}, salt={salt}, signature={signature}"
    )


class SolapiProvider(NotificationProvider):
    """SOLAPI 알림톡/SMS 발송. 키 게이트 + HMAC 인증 + 실패 매핑."""

    def __init__(
        self,
        api_key: str | None = None,
        api_secret: str | None = None,
        sender_key: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.solapi_api_key
        self.api_secret = api_secret if api_secret is not None else settings.solapi_api_secret
        self.sender_key = sender_key if sender_key is not None else settings.kakao_sender_key
        self.base_url = (base_url or settings.solapi_base_url).rstrip("/")
        self._timeout = httpx.Timeout(
            connect=settings.http_timeout_connect,
            read=settings.http_timeout_read,
            write=10.0,
            pool=10.0,
        )

    # ── 내부 ──────────────────────────────────────────────────────────────
    def _require_keys(self, *, need_template: bool) -> None:
        """키 미설정 시 명확한 RuntimeError(사업자·발신프로필·심사 선행)."""
        missing: list[str] = []
        if not self.api_key:
            missing.append("solapi_api_key")
        if not self.api_secret:
            missing.append("solapi_api_secret")
        if not self.sender_key:
            missing.append("kakao_sender_key(pfId)")
        if need_template and not settings.kakao_template_briefing:
            missing.append("kakao_template_briefing")
        if missing:
            raise RuntimeError(
                "SOLAPI 미설정: " + ", ".join(missing)
                + " — 사업자등록·발신프로필·템플릿 심사 후 주입 필요."
            )

    def _post(self, message: dict) -> dict:
        """HMAC 인증 헤더로 SOLAPI 단건 발송. 실패는 NotRegisteredOrBlocked/RuntimeError."""
        url = f"{self.base_url}{_SEND_PATH}"
        headers = {
            "Authorization": _hmac_auth_header(self.api_key, self.api_secret),
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json={"message": message}, headers=headers)
        except httpx.TransportError as exc:  # 연결 실패/타임아웃
            raise RuntimeError(f"SOLAPI 전송 실패(transport): {exc}") from exc

        if resp.status_code >= 500:
            raise RuntimeError(f"SOLAPI 서버 오류 http {resp.status_code}")

        payload = resp.json()

        # 단건 발송 실패는 4xx + statusCode/errorCode 로 내려옴.
        if resp.status_code >= 400:
            code = str(payload.get("errorCode") or payload.get("statusCode") or "")
            msg = str(payload.get("errorMessage") or payload.get("statusMessage") or "")
            if code in _FALLBACK_STATUS_CODES:
                raise NotRegisteredOrBlocked(f"{code}: {msg}")
            raise RuntimeError(f"SOLAPI 발송 실패 http {resp.status_code} {code}: {msg}")

        # 200이어도 statusCode 가 성공('2000')이 아니면 실패 매핑.
        status_code = str(payload.get("statusCode", "2000"))
        if status_code not in ("2000", "200"):
            status_msg = str(payload.get("statusMessage", ""))
            if status_code in _FALLBACK_STATUS_CODES:
                raise NotRegisteredOrBlocked(f"{status_code}: {status_msg}")
            raise RuntimeError(f"SOLAPI 발송 실패 {status_code}: {status_msg}")

        return payload

    @staticmethod
    def _msg_id(payload: dict) -> str:
        """응답에서 provider 메시지 ID 추출(groupId/messageId 방어적)."""
        return str(
            payload.get("messageId")
            or payload.get("groupId")
            or (payload.get("groupInfo") or {}).get("_id")
            or ""
        )

    # ── 공개 API ──────────────────────────────────────────────────────────
    def send_alimtalk(self, phone: str, template_code: str, variables: dict) -> SendResult:
        """알림톡 단건 발송. variables 는 템플릿 `#{}` 자리표시자 매핑(키=치환변수명)."""
        self._require_keys(need_template=True)
        message = {
            "to": phone,
            "type": "ATA",  # AlimTalk
            "kakaoOptions": {
                "pfId": self.sender_key,
                "templateId": template_code,
                # SOLAPI는 #{변수명} → variables 의 동일 키로 치환.
                "variables": {f"#{{{k}}}": str(v) for k, v in variables.items()},
            },
        }
        payload = self._post(message)
        return SendResult(provider_msg_id=self._msg_id(payload), channel="alimtalk")

    def send_sms(self, phone: str, text: str) -> SendResult:
        """SMS/LMS 폴백 발송(길이에 따라 SOLAPI가 자동 분류)."""
        self._require_keys(need_template=False)
        message = {"to": phone, "text": text, "type": "LMS"}
        payload = self._post(message)
        return SendResult(provider_msg_id=self._msg_id(payload), channel="sms")


def get_provider() -> NotificationProvider:
    return SolapiProvider()
