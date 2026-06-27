"""결제 제공자 추상화 — Toss 정기결제(빌링키). 정본: docs/04-architecture/billing.md.

🚧 사업자등록·Toss 가맹 심사 전 = test 모드만. 실키 주입 시 live 동작하도록 격리.
active_subscribed = subscriptions.status IN ('active','trialing').
인증: Authorization: Basic base64(secretKey:). 키 미설정 시 RuntimeError.
외부 HTTP는 httpx.Client(테스트는 MockTransport로 모킹, 실호출 금지).
"""
from __future__ import annotations

import base64
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

_TOSS_BASE_URL = "https://api.tosspayments.com"
_ISSUE_PATH = "/v1/billing/authorizations/issue"


@dataclass
class ChargeResult:
    payment_key: str
    status: str


class PaymentProvider(ABC):
    @abstractmethod
    def issue_billing_key(self, customer_key: str, auth_key: str) -> str: ...

    @abstractmethod
    def charge(
        self,
        billing_key: str,
        amount: int,
        order_id: str,
        order_name: str,
        customer_key: str,
    ) -> ChargeResult: ...

    @abstractmethod
    def handle_webhook(self, payload: dict) -> dict: ...


class TossProvider(PaymentProvider):
    """Toss 빌링 API 연결. 테스트 키로 골격 검증, 실키는 사업자 확보 후."""

    def __init__(self, secret_key: str | None = None, base_url: str | None = None) -> None:
        self.secret_key = secret_key if secret_key is not None else settings.toss_secret_key
        self.base_url = (base_url or _TOSS_BASE_URL).rstrip("/")
        self._timeout = httpx.Timeout(
            connect=settings.http_timeout_connect,
            read=settings.http_timeout_read,
            write=10.0,
            pool=10.0,
        )

    # ── 내부 ──────────────────────────────────────────────────────────────
    def _require_key(self) -> None:
        if not self.secret_key:
            raise RuntimeError(
                "TOSS_SECRET_KEY 미설정 — 사업자등록·Toss 가맹 후 (test 키)부터 주입 필요."
            )

    def _auth_header(self) -> str:
        """Authorization: Basic base64(secretKey:). ⚠️ secret 로그 금지."""
        token = base64.b64encode(f"{self.secret_key}:".encode("utf-8")).decode("ascii")
        return f"Basic {token}"

    def _post(self, path: str, body: dict) -> dict:
        url = f"{self.base_url}{path}"
        headers = {"Authorization": self._auth_header(), "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, json=body, headers=headers)
        except httpx.TransportError as exc:
            raise RuntimeError(f"Toss 전송 실패(transport): {exc}") from exc

        if resp.status_code >= 500:
            raise RuntimeError(f"Toss 서버 오류 http {resp.status_code}")

        payload = resp.json()
        if resp.status_code >= 400:
            code = str(payload.get("code", ""))
            msg = str(payload.get("message", ""))
            raise RuntimeError(f"Toss API 오류 http {resp.status_code} {code}: {msg}")
        return payload

    # ── 공개 API ──────────────────────────────────────────────────────────
    def issue_billing_key(self, customer_key: str, auth_key: str) -> str:
        """빌링키 발급(POST /v1/billing/authorizations/issue). 빌링키 문자열 반환.

        ⚠️ 반환된 빌링키는 로그에 남기지 않는다(시크릿).
        """
        self._require_key()
        payload = self._post(
            _ISSUE_PATH, {"authKey": auth_key, "customerKey": customer_key}
        )
        billing_key = payload.get("billingKey")
        if not billing_key:
            raise RuntimeError("Toss 빌링키 발급 응답에 billingKey 없음")
        return str(billing_key)

    def charge(
        self,
        billing_key: str,
        amount: int,
        order_id: str,
        order_name: str,
        customer_key: str,
    ) -> ChargeResult:
        """정기결제 승인(POST /v1/billing/{billingKey})."""
        self._require_key()
        payload = self._post(
            f"/v1/billing/{billing_key}",
            {
                "amount": amount,
                "orderId": order_id,
                "orderName": order_name,
                "customerKey": customer_key,
            },
        )
        return ChargeResult(
            payment_key=str(payload.get("paymentKey", "")),
            status=str(payload.get("status", "")),
        )

    def handle_webhook(self, payload: dict) -> dict:
        """웹훅 상태 파싱. eventType + data.{orderId,status,paymentKey} 추출.

        TODO(검증): 웹훅 서명 검증(헤더 시크릿)은 라우터/서비스에서 추가.
        """
        data = payload.get("data") or {}
        return {
            "event_type": payload.get("eventType"),
            "order_id": data.get("orderId"),
            "status": data.get("status"),
            "payment_key": data.get("paymentKey"),
        }


def get_provider() -> PaymentProvider:
    return TossProvider()


def active_subscribed(status: str | None) -> bool:
    """구독 게이트: subscriptions.status IN ('active','trialing')."""
    return status in ("active", "trialing")
