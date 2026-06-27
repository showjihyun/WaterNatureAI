"""단위: SolapiProvider — HMAC 서명 헤더 · 키게이트 RuntimeError · 실패 매핑.

외부 HTTP 실호출 금지 → httpx.MockTransport 로 모킹. 키 없는 CI 통과.
"""
from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from app.services.notifications.provider import (
    NotRegisteredOrBlocked,
    SolapiProvider,
    _hmac_auth_header,
)


_RealClient = httpx.Client


def _mock_client(handler):
    """httpx.Client(...) 호출이 MockTransport 기반 클라이언트를 반환하도록 patch."""
    def _factory(*_a, **kwargs):
        kwargs.pop("transport", None)
        return _RealClient(transport=httpx.MockTransport(handler), **kwargs)

    return patch("app.services.notifications.provider.httpx.Client", _factory)


def _provider() -> SolapiProvider:
    return SolapiProvider(
        api_key="KEY", api_secret="SECRET", sender_key="PF", base_url="https://api.test"
    )


# ── HMAC 서명 헤더 ──────────────────────────────────────────────────────────

class TestHmacHeader:
    def test_header_shape(self):
        header = _hmac_auth_header("mykey", "mysecret")
        assert header.startswith("HMAC-SHA256 ")
        assert "apiKey=mykey" in header
        assert "date=" in header
        assert "salt=" in header
        assert "signature=" in header

    def test_secret_not_in_header(self):
        """시크릿 원문이 헤더에 노출되지 않는다(서명만)."""
        header = _hmac_auth_header("mykey", "supersecret")
        assert "supersecret" not in header

    def test_signature_deterministic_for_same_date_salt(self):
        import hashlib
        import hmac

        date = "2026-06-20T00:00:00.000Z"
        salt = "abc"
        expected = hmac.new(b"sec", (date + salt).encode(), hashlib.sha256).hexdigest()
        actual = hmac.new(b"sec", (date + salt).encode(), hashlib.sha256).hexdigest()
        assert actual == expected


# ── 키 게이트 ────────────────────────────────────────────────────────────────

class TestKeyGate:
    def test_missing_api_key_raises(self):
        prov = SolapiProvider(api_key="", api_secret="S", sender_key="PF")
        with pytest.raises(RuntimeError, match="solapi_api_key"):
            prov.send_alimtalk("01012345678", "TMPL", {"회사명": "A"})

    def test_missing_secret_raises(self):
        prov = SolapiProvider(api_key="K", api_secret="", sender_key="PF")
        with pytest.raises(RuntimeError, match="solapi_api_secret"):
            prov.send_alimtalk("01012345678", "TMPL", {"회사명": "A"})

    def test_missing_sender_key_raises(self):
        prov = SolapiProvider(api_key="K", api_secret="S", sender_key="")
        with pytest.raises(RuntimeError, match="kakao_sender_key"):
            prov.send_alimtalk("01012345678", "TMPL", {"회사명": "A"})

    def test_missing_template_raises(self):
        prov = _provider()
        with patch("app.services.notifications.provider.settings") as s:
            s.kakao_template_briefing = ""
            with pytest.raises(RuntimeError, match="kakao_template_briefing"):
                prov.send_alimtalk("01012345678", "", {"회사명": "A"})


# ── 발송 성공/실패 매핑 ──────────────────────────────────────────────────────

class TestSendAlimtalk:
    def test_success(self):
        captured: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["auth"] = request.headers.get("authorization")
            captured["url"] = str(request.url)
            return httpx.Response(200, json={"statusCode": "2000", "messageId": "M123"})

        with patch(
            "app.services.notifications.provider.settings"
        ) as s, _mock_client(handler):
            s.kakao_template_briefing = "TMPL"
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            res = _provider().send_alimtalk("01012345678", "TMPL", {"회사명": "A", "건수": 2})

        assert res.channel == "alimtalk"
        assert res.provider_msg_id == "M123"
        # HMAC 서명 헤더가 실제로 붙는다.
        assert captured["auth"].startswith("HMAC-SHA256 ")

    def test_failure_maps_to_not_registered(self):
        """폴백 대상 코드(3008 등) → NotRegisteredOrBlocked."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"statusCode": "3008", "statusMessage": "발신프로필 미등록"})

        with patch(
            "app.services.notifications.provider.settings"
        ) as s, _mock_client(handler):
            s.kakao_template_briefing = "TMPL"
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            with pytest.raises(NotRegisteredOrBlocked):
                _provider().send_alimtalk("01012345678", "TMPL", {"회사명": "A"})

    def test_http_400_other_error_raises_runtime(self):
        """폴백 대상 아닌 4xx → RuntimeError."""
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(400, json={"errorCode": "9999", "errorMessage": "잘못된 요청"})

        with patch(
            "app.services.notifications.provider.settings"
        ) as s, _mock_client(handler):
            s.kakao_template_briefing = "TMPL"
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            with pytest.raises(RuntimeError):
                _provider().send_alimtalk("01012345678", "TMPL", {"회사명": "A"})

    def test_5xx_raises_runtime(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(503, json={})

        with patch(
            "app.services.notifications.provider.settings"
        ) as s, _mock_client(handler):
            s.kakao_template_briefing = "TMPL"
            s.http_timeout_connect = 5.0
            s.http_timeout_read = 30.0
            with pytest.raises(RuntimeError, match="서버 오류"):
                _provider().send_alimtalk("01012345678", "TMPL", {"회사명": "A"})
