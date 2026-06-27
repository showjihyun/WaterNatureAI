"""data.go.kr 계열 REST 클라이언트 (httpx). 재시도/타임아웃/페이지 파싱.

정본: collector-narajangter.md §5.
TODO(검증): 소스별 응답 envelope(response.body.items 등) 구조를 명세로 확정.
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TransientError(RuntimeError):
    """재시도 가능한 일시 오류(5xx/타임아웃/일시 resultCode)."""


class DataGoKrApiError(RuntimeError):
    """data.go.kr API 오류 — resultCode != '00' 비재시도 류(인증/파라미터 등).

    인증/쿼터/파라미터 오류 → 즉시 실패 + Sentry 알림 대상.
    """

    def __init__(self, result_code: str, result_msg: str) -> None:
        super().__init__(f"data.go.kr API error: {result_code} / {result_msg}")
        self.result_code = result_code
        self.result_msg = result_msg


# data.go.kr 공공데이터포털 표준 resultCode (검증 완료: 표준 오류코드표).
#   00 NORMAL / 01 APPLICATION_ERROR / 02 DB_ERROR / 03 NODATA_ERROR /
#   04 HTTP_ERROR / 05 SERVICETIMEOUT_ERROR /
#   10 INVALID_REQUEST_PARAMETER / 11 NO_MANDATORY_REQUEST_PARAMETERS /
#   12 NO_OPENAPI_SERVICE_ERROR /
#   20 SERVICE_ACCESS_DENIED / 21 TEMPORARILY_DISABLE_THE_SERVICEKEY /
#   22 LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS (쿼터 초과) /
#   30 SERVICE_KEY_IS_NOT_REGISTERED / 31 DEADLINE_HAS_EXPIRED /
#   32 UNREGISTERED_IP / 33 UNSIGNED_CALL / 99 UNKNOWN_ERROR
# 출처: 공공데이터포털 OpenAPI 표준 에러코드(문화포털/포털 가이드 등 공통).

# 데이터 없음 → 빈 리스트로 처리(레코드 없음은 정상).
_NODATA_CODES: frozenset[str] = frozenset({"03"})

# 일시 오류(서버측/타임아웃 류) → 재시도. 그 외 비'00'은 비재시도(DataGoKrApiError).
#   02 DB_ERROR, 04 HTTP_ERROR, 05 SERVICETIMEOUT, 01 APPLICATION_ERROR는
#   서버측 일시 장애일 가능성이 높아 보수적으로 재시도 대상에 포함.
_TRANSIENT_CODES: frozenset[str] = frozenset({"01", "02", "04", "05"})


class DataGoKrClient:
    """data.go.kr 서비스 공통 HTTP 클라이언트.

    - 5xx/transport 오류 → TransientError (Celery autoretry)
    - resultCode != '00' && NODATA_CODE → 빈 리스트 반환
    - resultCode != '00' && 기타 → DataGoKrApiError (비재시도)
    """

    def __init__(self, base_url: str, service_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self._timeout = httpx.Timeout(
            connect=settings.http_timeout_connect,
            read=settings.http_timeout_read,
            write=10.0,
            pool=10.0,
        )

    def get(self, operation: str, params: dict[str, Any]) -> dict:
        """HTTP GET → JSON dict. 오류는 TransientError / DataGoKrApiError 로 분리."""
        url = f"{self.base_url}/{operation}"
        q = {"serviceKey": self.service_key, "type": "json", **params}
        try:
            resp = httpx.get(url, params=q, timeout=self._timeout)
        except httpx.TransportError as exc:  # 연결 실패/타임아웃 → 재시도
            raise TransientError(str(exc)) from exc

        if resp.status_code >= 500:
            raise TransientError(f"http {resp.status_code}")

        resp.raise_for_status()
        payload = resp.json()

        # envelope 파싱 → resultCode 검사
        header = (payload.get("response") or {}).get("header") or {}
        result_code: str = str(header.get("resultCode", "00"))
        result_msg: str = str(header.get("resultMsg", ""))

        if result_code != "00":
            # 03 NODATA → 데이터 없음(정상), 빈 리스트로 처리.
            if result_code in _NODATA_CODES:
                logger.debug(
                    "data.go.kr NODATA: op=%s code=%s msg=%s", operation, result_code, result_msg
                )
                return payload  # items()가 빈 리스트 반환하도록 그대로 통과

            # 서버측 일시 장애(01/02/04/05) → 재시도.
            if result_code in _TRANSIENT_CODES:
                logger.warning(
                    "data.go.kr transient API error: op=%s code=%s msg=%s",
                    operation, result_code, result_msg,
                )
                raise TransientError(f"resultCode {result_code}: {result_msg}")

            # 인증/쿼터/파라미터 오류(10·11·12·20·21·22·30·31·32·33·99) → 비재시도.
            logger.warning(
                "data.go.kr API error (non-retryable): op=%s code=%s msg=%s",
                operation, result_code, result_msg,
            )
            raise DataGoKrApiError(result_code, result_msg)

        return payload

    @staticmethod
    def total_count(payload: dict) -> int | None:
        """response.body.totalCount 추출. 없으면 None."""
        body = (payload.get("response") or {}).get("body") or {}
        val = body.get("totalCount")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def items(payload: dict) -> list[dict]:
        """response.body.items[.item] 추출 (구조 방어적).

        data.go.kr 응답은 3가지 형태:
        1. items: [{...}, ...] — 복수 목록
        2. items: {"item": [{...}]} — 중첩 dict
        3. items: {"item": {...}} — 단건 dict (단건일 때 list가 아닌 dict로 오는 경우)

        TODO(검증): 소스별 실응답으로 형태 최종 확인.
        """
        body = (payload.get("response") or {}).get("body") or {}
        items = body.get("items")

        if items is None:
            return []

        # 빈 문자열("") — NODATA 응답 시 발생 가능
        if items == "" or items == {}:
            return []

        if isinstance(items, dict):
            inner = items.get("item", [])
            if isinstance(inner, dict):  # 단건
                return [inner]
            return inner if isinstance(inner, list) else []

        if isinstance(items, list):
            return items

        return []


class NtisClient:
    """NTIS 15074634(과기정통부 사업공고) **비표준 JSON envelope** 클라이언트.

    라이브 실측(2026-06-23): returnType=json 응답이 표준 `{response:{header,body}}`가
    아니라 XML→JSON 변환 산물인 **배열형**이다:
        {"response": [ {"header": {...}}, {"body": {"pageNo","totalCount","items":[...]}} ]}
    또한 items는 `[{"item": {...}}, {"item": {...}}, ...]` (각 원소가 item 래퍼).
    표준 DataGoKrClient.get/items는 response를 dict로 가정해 깨지므로 전용 클라이언트로 분리.
    (returnType=xml은 표준 XML이나, JSON 경로 유지를 위해 배열형을 파싱.)
    """

    def __init__(self, base_url: str, service_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self._timeout = httpx.Timeout(
            connect=settings.http_timeout_connect,
            read=settings.http_timeout_read,
            write=10.0,
            pool=10.0,
        )

    @staticmethod
    def _find(parts: Any, key: str) -> dict:
        """response(list 또는 dict)에서 주어진 키를 가진 하위 dict 반환."""
        if isinstance(parts, list):
            for part in parts:
                if isinstance(part, dict) and key in part:
                    val = part.get(key)
                    return val if isinstance(val, dict) else {}
            return {}
        if isinstance(parts, dict):
            val = parts.get(key)
            return val if isinstance(val, dict) else {}
        return {}

    def get(self, operation: str, params: dict[str, Any]) -> dict:
        """HTTP GET → JSON dict(배열형 envelope). resultCode 검사 후 반환."""
        url = f"{self.base_url}/{operation}"
        q = {"serviceKey": self.service_key, "returnType": "json", **params}
        try:
            resp = httpx.get(url, params=q, timeout=self._timeout)
        except httpx.TransportError as exc:
            raise TransientError(str(exc)) from exc

        if resp.status_code >= 500:
            raise TransientError(f"http {resp.status_code}")
        if resp.status_code == 403:
            raise DataGoKrApiError("403", "Forbidden — data.go.kr 활용신청/키 승인 필요")
        resp.raise_for_status()
        payload = resp.json()

        header = self._find(payload.get("response"), "header")
        result_code = str(header.get("resultCode", "00"))
        result_msg = str(header.get("resultMsg", ""))
        if result_code != "00":
            if result_code in _NODATA_CODES:
                return payload
            if result_code in _TRANSIENT_CODES:
                raise TransientError(f"resultCode {result_code}: {result_msg}")
            raise DataGoKrApiError(result_code, result_msg)
        return payload

    @classmethod
    def items(cls, payload: dict) -> list[dict]:
        """response[].body.items[] → 각 {"item": {...}} 래퍼 평탄화."""
        body = cls._find(payload.get("response"), "body")
        items = body.get("items")
        if not items:
            return []
        out: list[dict] = []
        seq = items if isinstance(items, list) else [items]
        for el in seq:
            if not isinstance(el, dict):
                continue
            inner = el.get("item", el)  # {"item": {...}} 래퍼 or 이미 평탄
            if isinstance(inner, dict):
                out.append(inner)
            elif isinstance(inner, list):
                out.extend(x for x in inner if isinstance(x, dict))
        return out

    @classmethod
    def total_count(cls, payload: dict) -> int | None:
        """response[].body.totalCount."""
        body = cls._find(payload.get("response"), "body")
        val = body.get("totalCount")
        try:
            return int(val) if val is not None else None
        except (ValueError, TypeError):
            return None


class KStartupClient:
    """K-Startup B552735 신형 **평면형** 응답 클라이언트.

    표준 data.go.kr envelope(response.body.items) 가 아니라
    `{"data": [...], "totalCount": N, "page": p, "perPage": n, "matchCount": m}`
    형태(라이브 프로브 2026-06-22로 envelope=평면형 확정; 단 403=활용신청 필요).
    필드명은 B552735 공식 스키마 기반(키 승인 후 실측 1회 확인 권장).
    """

    def __init__(self, base_url: str, service_key: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.service_key = service_key
        self._timeout = httpx.Timeout(
            connect=settings.http_timeout_connect,
            read=settings.http_timeout_read,
            write=10.0,
            pool=10.0,
        )

    def get(self, operation: str, params: dict[str, Any]) -> dict:
        """HTTP GET → JSON dict(평면형). 5xx/transport→TransientError, 403→DataGoKrApiError."""
        url = f"{self.base_url}/{operation}"
        q = {"serviceKey": self.service_key, "returnType": "json", **params}
        try:
            resp = httpx.get(url, params=q, timeout=self._timeout)
        except httpx.TransportError as exc:
            raise TransientError(str(exc)) from exc

        if resp.status_code >= 500:
            raise TransientError(f"http {resp.status_code}")
        # 403: 인증키가 이 API에 활용신청/승인되지 않음(비재시도).
        if resp.status_code == 403:
            raise DataGoKrApiError("403", "Forbidden — data.go.kr 활용신청/키 승인 필요")
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def items(payload: dict) -> list[dict]:
        """공고 목록 추출 — envelope 3형태 방어적 처리.

        서비스설계서(v2.0)는 응답을 `<items><item>…`(표준 스타일)로 표기하나
        JSON 정확 형태는 403(활용신청)으로 미확인 → 모두 대응:
          1. uddi 평면형: `{"data": [...]}`
          2. 단순형:       `{"items": {"item": [...]}}` 또는 `{"items": [...]}`
          3. 표준형:       `{"response": {"body": {"items": …}}}`
        """
        data = payload.get("data")
        if isinstance(data, list):
            return data
        items = payload.get("items")
        if items is not None:
            if isinstance(items, list):
                return items
            if isinstance(items, dict):
                inner = items.get("item")
                if isinstance(inner, dict):
                    return [inner]
                return inner if isinstance(inner, list) else []
        return DataGoKrClient.items(payload)

    @staticmethod
    def total_count(payload: dict) -> int | None:
        """총건수 추출 — totalCount/matchCount(평면형) → 표준 envelope 순."""
        for key in ("totalCount", "matchCount"):
            val = payload.get(key)
            if val is not None:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
        return DataGoKrClient.total_count(payload)
