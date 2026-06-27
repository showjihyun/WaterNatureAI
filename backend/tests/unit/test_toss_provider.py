"""단위: TossProvider — 빌링키 발급 · charge · 키게이트 RuntimeError.

외부 HTTP 실호출 금지 → httpx.MockTransport 로 모킹.
"""
from __future__ import annotations

import base64
from unittest.mock import patch

import httpx
import pytest

from app.services.billing.provider import TossProvider, active_subscribed


_RealClient = httpx.Client


def _mock_client(handler):
    def _factory(*_a, **kwargs):
        kwargs.pop("transport", None)
        return _RealClient(transport=httpx.MockTransport(handler), **kwargs)

    return patch("app.services.billing.provider.httpx.Client", _factory)


def _provider() -> TossProvider:
    return TossProvider(secret_key="test_sk_xxx", base_url="https://api.test")


def _patch_settings():
    s = patch("app.services.billing.provider.settings")
    return s


# ── 키 게이트 ────────────────────────────────────────────────────────────────

class TestKeyGate:
    def test_issue_billing_key_no_secret_raises(self):
        prov = TossProvider(secret_key="")
        with pytest.raises(RuntimeError, match="TOSS_SECRET_KEY"):
            prov.issue_billing_key("cust_1", "auth_1")

    def test_charge_no_secret_raises(self):
        prov = TossProvider(secret_key="")
        with pytest.raises(RuntimeError, match="TOSS_SECRET_KEY"):
            prov.charge("bk_1", 99000, "order_1", "Basic", "cust_1")


# ── 인증 헤더 ────────────────────────────────────────────────────────────────

class TestAuthHeader:
    def test_basic_auth_base64(self):
        prov = TossProvider(secret_key="sk_abc")
        header = prov._auth_header()
        assert header.startswith("Basic ")
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode()
        assert decoded == "sk_abc:"  # secret + ':' (Toss 규약)


# ── 빌링키 발급 ──────────────────────────────────────────────────────────────

class TestIssueBillingKey:
    def test_success_returns_billing_key(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("authorization")
            return httpx.Response(200, json={"billingKey": "bk_live_123", "card": {}})

        with _patch_settings() as s, _mock_client(handler):
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            bk = _provider().issue_billing_key("cust_1", "auth_1")

        assert bk == "bk_live_123"
        assert "/v1/billing/authorizations/issue" in captured["url"]
        assert captured["auth"].startswith("Basic ")

    def test_missing_billing_key_in_response_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"unexpected": True})

        with _patch_settings() as s, _mock_client(handler):
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            with pytest.raises(RuntimeError, match="billingKey 없음"):
                _provider().issue_billing_key("cust_1", "auth_1")

    def test_4xx_raises_runtime(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"code": "INVALID_AUTH_KEY", "message": "bad"})

        with _patch_settings() as s, _mock_client(handler):
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            with pytest.raises(RuntimeError, match="Toss API 오류"):
                _provider().issue_billing_key("cust_1", "auth_1")


# ── 정기결제 charge ──────────────────────────────────────────────────────────

class TestCharge:
    def test_success(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            return httpx.Response(
                200, json={"paymentKey": "pay_123", "status": "DONE", "orderId": "order_1"}
            )

        with _patch_settings() as s, _mock_client(handler):
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            res = _provider().charge("bk_1", 99000, "order_1", "Basic 구독", "cust_1")

        assert res.payment_key == "pay_123"
        assert res.status == "DONE"
        assert "/v1/billing/bk_1" in captured["url"]

    def test_charge_failure_raises(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"code": "REJECT_CARD", "message": "card rejected"})

        with _patch_settings() as s, _mock_client(handler):
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            with pytest.raises(RuntimeError):
                _provider().charge("bk_1", 99000, "order_1", "Basic", "cust_1")


# ── 웹훅 파싱 ────────────────────────────────────────────────────────────────

class TestWebhook:
    def test_parse(self):
        prov = TossProvider(secret_key="x")
        event = prov.handle_webhook(
            {"eventType": "PAYMENT_STATUS_CHANGED",
             "data": {"orderId": "o1", "status": "DONE", "paymentKey": "pk1"}}
        )
        assert event["event_type"] == "PAYMENT_STATUS_CHANGED"
        assert event["order_id"] == "o1"
        assert event["status"] == "DONE"
        assert event["payment_key"] == "pk1"


# ── active_subscribed ────────────────────────────────────────────────────────

class TestActiveSubscribed:
    def test_active(self):
        assert active_subscribed("active") is True

    def test_trialing(self):
        assert active_subscribed("trialing") is True

    def test_past_due(self):
        assert active_subscribed("past_due") is False

    def test_none(self):
        assert active_subscribed(None) is False
