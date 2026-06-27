"""단위 테스트: DataGoKrClient — envelope 파싱 / items 추출 / 오류 분기.

HTTP를 직접 모킹(monkeypatch). respx 등 추가 의존성 불필요.
정본: collector-narajangter.md §5 / client.py.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from app.services.collectors.client import (
    DataGoKrApiError,
    DataGoKrClient,
    KStartupClient,
    NtisClient,
    TransientError,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _make_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    """httpx.Response를 최소한으로 흉내내는 mock 객체 생성."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.json.return_value = json_data
    # raise_for_status는 4xx/5xx에서만 예외 — 여기서는 status_code >= 500이 먼저 분기됨
    if status_code < 400:
        mock.raise_for_status.return_value = None
    else:
        mock.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock
        )
    return mock


@pytest.fixture()
def client() -> DataGoKrClient:
    return DataGoKrClient("https://example.api/service", "testkey")


# ── items() 정적 메서드 ──────────────────────────────────────────────────

class TestClientItems:
    def test_list_items(self):
        payload = {
            "response": {"body": {"items": [{"a": 1}, {"b": 2}]}}
        }
        assert DataGoKrClient.items(payload) == [{"a": 1}, {"b": 2}]

    def test_nested_dict_item_list(self):
        """items: {"item": [...]} 형태."""
        payload = {
            "response": {"body": {"items": {"item": [{"id": "1"}, {"id": "2"}]}}}
        }
        assert DataGoKrClient.items(payload) == [{"id": "1"}, {"id": "2"}]

    def test_nested_dict_item_single(self):
        """items: {"item": {...}} — 단건 dict."""
        payload = {
            "response": {"body": {"items": {"item": {"id": "1"}}}}
        }
        result = DataGoKrClient.items(payload)
        assert result == [{"id": "1"}]

    def test_empty_string_items(self):
        """items: "" (NODATA 응답 시)."""
        payload = {
            "response": {"body": {"items": ""}}
        }
        assert DataGoKrClient.items(payload) == []

    def test_empty_dict_items(self):
        payload = {
            "response": {"body": {"items": {}}}
        }
        assert DataGoKrClient.items(payload) == []

    def test_none_items(self):
        payload = {"response": {"body": {}}}
        assert DataGoKrClient.items(payload) == []

    def test_missing_response(self):
        assert DataGoKrClient.items({}) == []

    def test_missing_body(self):
        assert DataGoKrClient.items({"response": {}}) == []


# ── total_count() 정적 메서드 ────────────────────────────────────────────

class TestClientTotalCount:
    def test_total_count(self):
        payload = {"response": {"body": {"totalCount": 42}}}
        assert DataGoKrClient.total_count(payload) == 42

    def test_string_total_count(self):
        payload = {"response": {"body": {"totalCount": "42"}}}
        assert DataGoKrClient.total_count(payload) == 42

    def test_missing_total_count(self):
        payload = {"response": {"body": {}}}
        assert DataGoKrClient.total_count(payload) is None

    def test_zero_total_count(self):
        payload = {"response": {"body": {"totalCount": 0}}}
        assert DataGoKrClient.total_count(payload) == 0


# ── get() — 정상 응답 ────────────────────────────────────────────────────

class TestClientGet:
    def test_normal_response(self, client, narajangter_envelope_multi):
        with patch("httpx.get", return_value=_make_response(narajangter_envelope_multi)):
            result = client.get("getBidPblancListInfoThng", {"pageNo": 1})
        items = DataGoKrClient.items(result)
        assert len(items) == 2

    def test_params_include_service_key(self, client, narajangter_envelope_multi):
        """serviceKey와 type=json이 파라미터에 포함되어야 함."""
        captured_params: dict = {}

        def fake_get(url, *, params, timeout):
            captured_params.update(params)
            return _make_response(narajangter_envelope_multi)

        with patch("httpx.get", side_effect=fake_get):
            client.get("op", {"pageNo": 1})

        assert captured_params["serviceKey"] == "testkey"
        assert captured_params["type"] == "json"
        assert captured_params["pageNo"] == 1


# ── get() — NODATA 분기 ──────────────────────────────────────────────────

class TestClientNodata:
    def test_nodata_code_returns_empty_items(
        self, client, narajangter_envelope_nodata
    ):
        """resultCode='03' → DataGoKrApiError 아님, items() → 빈 리스트."""
        with patch("httpx.get", return_value=_make_response(narajangter_envelope_nodata)):
            result = client.get("op", {})
        assert DataGoKrClient.items(result) == []


# ── get() — 인증/쿼터 오류 ──────────────────────────────────────────────

class TestClientApiError:
    def test_quota_error_raises_data_go_kr_api_error(
        self, client, narajangter_envelope_auth_error
    ):
        """resultCode='22'(쿼터 초과) → DataGoKrApiError (비재시도)."""
        with patch("httpx.get", return_value=_make_response(narajangter_envelope_auth_error)):
            with pytest.raises(DataGoKrApiError) as exc_info:
                client.get("op", {})
        assert exc_info.value.result_code == "22"

    @pytest.mark.parametrize("code", ["10", "11", "12", "20", "21", "30", "31", "32", "33", "99"])
    def test_non_retryable_codes_raise_api_error(self, client, code):
        """인증/파라미터/쿼터 코드 → DataGoKrApiError (비재시도)."""
        payload = {
            "response": {
                "header": {"resultCode": code, "resultMsg": f"ERR_{code}"},
                "body": {},
            }
        }
        with patch("httpx.get", return_value=_make_response(payload)):
            with pytest.raises(DataGoKrApiError):
                client.get("op", {})

    @pytest.mark.parametrize("code", ["01", "02", "04", "05"])
    def test_server_side_codes_raise_transient(self, client, code):
        """서버측 일시 장애 코드(01/02/04/05) → TransientError (재시도)."""
        payload = {
            "response": {
                "header": {"resultCode": code, "resultMsg": f"ERR_{code}"},
                "body": {},
            }
        }
        with patch("httpx.get", return_value=_make_response(payload)):
            with pytest.raises(TransientError):
                client.get("op", {})

    def test_unknown_error_code_raises_data_go_kr_api_error(self, client):
        """알 수 없는 resultCode → DataGoKrApiError."""
        payload = {
            "response": {
                "header": {"resultCode": "99", "resultMsg": "UNKNOWN_ERROR"},
                "body": {},
            }
        }
        with patch("httpx.get", return_value=_make_response(payload)):
            with pytest.raises(DataGoKrApiError):
                client.get("op", {})


# ── get() — 5xx / TransientError ────────────────────────────────────────

class TestClientTransient:
    def test_5xx_raises_transient(self, client):
        """HTTP 5xx → TransientError (재시도)."""
        with patch("httpx.get", return_value=_make_response({}, status_code=503)):
            with pytest.raises(TransientError) as exc_info:
                client.get("op", {})
        assert "503" in str(exc_info.value)

    def test_500_raises_transient(self, client):
        with patch("httpx.get", return_value=_make_response({}, status_code=500)):
            with pytest.raises(TransientError):
                client.get("op", {})

    def test_transport_error_raises_transient(self, client):
        """네트워크 오류(TransportError) → TransientError."""
        with patch("httpx.get", side_effect=httpx.TransportError("connection refused")):
            with pytest.raises(TransientError):
                client.get("op", {})

    def test_timeout_raises_transient(self, client):
        """타임아웃 → TransientError."""
        with patch(
            "httpx.get",
            side_effect=httpx.TransportError("ReadTimeout"),
        ):
            with pytest.raises(TransientError):
                client.get("op", {})


# ── 페이지네이션 통합 시뮬레이션 ────────────────────────────────────────

class TestClientPagination:
    """DataGoKrClient.get()을 몽키패치해 2페이지 후 NODATA로 끝나는 시나리오."""

    def _make_page(self, items: list[dict], total: int = 1000) -> dict:
        return {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                "body": {
                    "items": items,
                    "totalCount": total,
                    "numOfRows": 3,
                    "pageNo": 1,
                },
            }
        }

    def test_two_page_scenario(self, client):
        """3건 → 2건 페이지 (두 번째 페이지에서 len < numOfRows → 종료)."""
        page1_items = [{"bidNtceNo": f"N{i}"} for i in range(3)]
        page2_items = [{"bidNtceNo": "N3"}, {"bidNtceNo": "N4"}]

        responses = [
            _make_response(self._make_page(page1_items, total=5)),
            _make_response(self._make_page(page2_items, total=5)),
        ]
        call_count = 0

        def fake_get(url, *, params, timeout):
            nonlocal call_count
            resp = responses[call_count]
            call_count += 1
            return resp

        with patch("httpx.get", side_effect=fake_get):
            r1 = client.get("op", {"pageNo": 1, "numOfRows": 3})
            r2 = client.get("op", {"pageNo": 2, "numOfRows": 3})

        assert len(DataGoKrClient.items(r1)) == 3
        assert len(DataGoKrClient.items(r2)) == 2  # 마지막 페이지

    def test_nested_envelope_items_extracted(self, client, narajangter_envelope_nested_item):
        """단건 nested items.item dict → 리스트로 정상 추출."""
        with patch(
            "httpx.get", return_value=_make_response(narajangter_envelope_nested_item)
        ):
            result = client.get("op", {})
        items = DataGoKrClient.items(result)
        assert len(items) == 1
        assert items[0]["bidNtceNo"] == "20240600123"


# ── KStartupClient (B552735 평면형) ─────────────────────────────────────────

_KSTARTUP_FLAT = {
    "currentCount": 2,
    "matchCount": 100,
    "page": 1,
    "perPage": 2,
    "totalCount": 100,
    "data": [
        {"pbanc_sn": 174320, "biz_pbanc_nm": "2026 예비창업패키지", "pbanc_ntrp_nm": "창업진흥원",
         "supt_biz_clsfc": "예비창업", "supt_regin": "전국",
         "pbanc_rcpt_bgng_dt": "20260601", "pbanc_rcpt_end_dt": "20260630",
         "detl_pg_url": "https://www.k-startup.go.kr/..."},
        {"pbanc_sn": 174321, "biz_pbanc_nm": "초기창업패키지", "pbanc_ntrp_nm": "창업진흥원"},
    ],
}


class TestKStartupClient:
    """B552735 신형 평면형 응답({data, totalCount}) 파싱 + 403 처리."""

    def test_items_from_flat_data(self):
        assert len(KStartupClient.items(_KSTARTUP_FLAT)) == 2
        assert KStartupClient.items(_KSTARTUP_FLAT)[0]["biz_pbanc_nm"] == "2026 예비창업패키지"

    def test_items_missing_data(self):
        assert KStartupClient.items({}) == []
        assert KStartupClient.items({"data": None}) == []

    def test_items_from_standard_envelope(self):
        """표준 envelope({response:{body:{items:{item:[...]}}}})도 방어 처리."""
        payload = {"response": {"body": {"items": {"item": [{"pbanc_sn": 1}, {"pbanc_sn": 2}]}}}}
        assert len(KStartupClient.items(payload)) == 2

    def test_items_from_simple_items_list(self):
        """단순형({items:[...]}) / 단건({items:{item:{...}}})도 처리."""
        assert KStartupClient.items({"items": [{"a": 1}]}) == [{"a": 1}]
        assert KStartupClient.items({"items": {"item": {"a": 1}}}) == [{"a": 1}]

    def test_total_count_flat(self):
        assert KStartupClient.total_count(_KSTARTUP_FLAT) == 100
        assert KStartupClient.total_count({}) is None

    def test_total_count_from_standard_envelope(self):
        assert KStartupClient.total_count({"response": {"body": {"totalCount": 7}}}) == 7

    def test_get_returns_flat_json(self):
        client = KStartupClient("https://apis.data.go.kr/B552735/x", "k")
        with patch("httpx.get", return_value=_make_response(_KSTARTUP_FLAT)):
            r = client.get("getAnnouncementInformation01", {"page": 1, "perPage": 2})
        assert KStartupClient.total_count(r) == 100
        assert len(KStartupClient.items(r)) == 2

    def test_403_raises_api_error(self):
        """활용신청 미승인 → 403 → DataGoKrApiError(비재시도)."""
        client = KStartupClient("https://apis.data.go.kr/B552735/x", "k")
        with patch("httpx.get", return_value=_make_response({}, status_code=403)):
            with pytest.raises(DataGoKrApiError) as exc:
                client.get("op", {})
        assert exc.value.result_code == "403"

    def test_5xx_raises_transient(self):
        client = KStartupClient("https://apis.data.go.kr/B552735/x", "k")
        with patch("httpx.get", return_value=_make_response({}, status_code=503)):
            with pytest.raises(TransientError):
                client.get("op", {})

    def test_transport_error_raises_transient(self):
        client = KStartupClient("https://apis.data.go.kr/B552735/x", "k")
        with patch("httpx.get", side_effect=httpx.TransportError("refused")):
            with pytest.raises(TransientError):
                client.get("op", {})


# ── NtisClient: 비표준 배열형 envelope (라이브 실측 2026-06-23) ──────────────────

# response=[{header},{body}], items=[{"item":{...}}, ...]
_NTIS_LIVE = {
    "response": [
        {"header": {"resultCode": "00", "resultMsg": "NORMAL_CODE"}},
        {"body": {
            "pageNo": "1",
            "totalCount": 4165,
            "items": [
                {"item": {
                    "subject": "2026년 공공연구성과 활용 촉진 R&D 공고",
                    "viewUrl": "https://www.msit.go.kr/bbs/view.do?nttSeqNo=3186789",
                    "deptName": "연구성과일자리정책과",
                    "pressDt": "2026-06-23",
                }},
                {"item": {
                    "subject": "2026년 차세대 통신 기술개발 공고",
                    "viewUrl": "https://www.msit.go.kr/bbs/view.do?nttSeqNo=3186786",
                    "deptName": "정보통신산업정책과",
                    "pressDt": "2026-06-22",
                }},
            ],
        }},
    ]
}


class TestNtisClientEnvelope:
    def test_items_flattens_item_wrappers(self):
        items = NtisClient.items(_NTIS_LIVE)
        assert len(items) == 2
        assert items[0]["subject"].startswith("2026년 공공연구성과")
        assert "nttSeqNo=3186789" in items[0]["viewUrl"]
        assert items[1]["deptName"] == "정보통신산업정책과"

    def test_total_count_from_body(self):
        assert NtisClient.total_count(_NTIS_LIVE) == 4165

    def test_empty_items_returns_empty(self):
        payload = {"response": [{"header": {"resultCode": "00"}}, {"body": {"items": ""}}]}
        assert NtisClient.items(payload) == []

    def test_single_item_not_in_list(self):
        """items가 단일 {"item":{...}} dict로 오는 경우도 방어."""
        payload = {"response": [
            {"header": {"resultCode": "00"}},
            {"body": {"items": {"item": {"subject": "단건"}}}},
        ]}
        items = NtisClient.items(payload)
        assert len(items) == 1 and items[0]["subject"] == "단건"

    def test_get_ok_returns_payload(self):
        client = NtisClient("http://apis.data.go.kr/1721000/msitannouncementinfo", "k")
        with patch("httpx.get", return_value=_make_response(_NTIS_LIVE)):
            payload = client.get("businessAnnouncMentList", {"pageNo": 1})
        assert NtisClient.total_count(payload) == 4165

    def test_get_nodata_code_returns_payload_empty_items(self):
        nodata = {"response": [{"header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"}}]}
        client = NtisClient("http://x/y", "k")
        with patch("httpx.get", return_value=_make_response(nodata)):
            payload = client.get("op", {})
        assert NtisClient.items(payload) == []

    def test_get_auth_error_raises(self):
        err = {"response": [{"header": {"resultCode": "30", "resultMsg": "SERVICE_KEY_IS_NOT_REGISTERED"}}]}
        client = NtisClient("http://x/y", "k")
        with patch("httpx.get", return_value=_make_response(err)):
            with pytest.raises(DataGoKrApiError):
                client.get("op", {})

    def test_get_403_raises_apierror(self):
        client = NtisClient("http://x/y", "k")
        with patch("httpx.get", return_value=_make_response({}, status_code=403)):
            with pytest.raises(DataGoKrApiError) as exc:
                client.get("op", {})
        assert exc.value.result_code == "403"
