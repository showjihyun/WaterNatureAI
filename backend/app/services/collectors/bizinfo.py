"""기업마당(Bizinfo) 지원사업 수집기 (P0 2순위).

정본: collector-base-bizinfo.md §3·§4 / docs/06 검증.
- 엔드포인트: 단일 `uss/rss/bizinfoApi.do` (data.go.kr와 다른 자체 키 crtfcKey).
- envelope: {"jsonArray":[...]} 평면 구조 (data.go.kr 표준 아님). 인증실패: {"reqErr":...}.
- 서버 날짜필터 없음 → creatPnttm 기준 역순 cutoff (검증 완료).
- 예산/자격은 목록에 없음 → requires_detail=True (상세 본문 추출은 enrich_detail).

필드명 검증(2026-06, 라이브 호출 + 오픈소스 교차확인):
  pblancId·pblancNm·jrsdInsttNm·excInsttNm·reqstBeginEndDe·creatPnttm·
  pldirSportRealmLclasCodeNm·pblancUrl(절대경로). creatPnttm='YYYY-MM-DD HH:MM:SS'.
  reqstBeginEndDe='YYYY-MM-DD ~ YYYY-MM-DD'(90%) + 비정형 10%.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from itertools import count
from typing import Any

import httpx

from app.core.config import settings
from app.services.collectors.base import BaseCollector, OpportunityDTO, _Window
from app.services.collectors.client import DataGoKrApiError, TransientError
from app.services.collectors.normalize import (
    derive_status,
    parse_kst,
    sha256_norm,
    split_reqst_period,
)

logger = logging.getLogger(__name__)

SOURCE_CODE = "bizinfo"


class BizinfoClient:
    """기업마당 정책정보 API 클라이언트.

    응답 envelope이 data.go.kr과 달라 별도 파싱:
      성공 → {"jsonArray": [ {...}, ... ]}
      인증실패 → {"reqErr": "존재하지 않는 인증키 입니다."} (HTTP 200)
    5xx/transport → TransientError, reqErr → DataGoKrApiError(비재시도).
    """

    def __init__(self, base_url: str, crtfc_key: str) -> None:
        self.base_url = base_url
        self.crtfc_key = crtfc_key
        self._timeout = httpx.Timeout(
            connect=settings.http_timeout_connect,
            read=settings.http_timeout_read,
            write=10.0,
            pool=10.0,
        )

    def fetch(self, page_index: int, page_unit: int) -> list[dict]:
        """한 페이지 목록 조회 → item 리스트. 검색은 등록일 최신순(서버 기본)."""
        params: dict[str, Any] = {
            "crtfcKey": self.crtfc_key,
            "dataType": "json",      # 검증: 'xml' 아니라 'rss'|'json'
            "pageIndex": page_index,
            "pageUnit": page_unit,
        }
        try:
            resp = httpx.get(self.base_url, params=params, timeout=self._timeout)
        except httpx.TransportError as exc:
            raise TransientError(str(exc)) from exc

        if resp.status_code >= 500:
            raise TransientError(f"http {resp.status_code}")
        resp.raise_for_status()
        payload = resp.json()

        # 인증/요청 오류 (HTTP 200 + reqErr) → 비재시도
        if isinstance(payload, dict) and payload.get("reqErr"):
            msg = str(payload["reqErr"])
            logger.warning("bizinfo reqErr (non-retryable): %s", msg)
            raise DataGoKrApiError("reqErr", msg)

        return self.items(payload)

    @staticmethod
    def items(payload: Any) -> list[dict]:
        """{"jsonArray":[...]} 추출 (방어적)."""
        if isinstance(payload, dict):
            arr = payload.get("jsonArray")
            if isinstance(arr, list):
                return arr
            return []
        if isinstance(payload, list):  # 혹시 평면 배열로 오는 경우
            return payload
        return []


def _build_stub_desc(raw: dict) -> str | None:
    """상세 보강 전 임시 description (분야 + 지원대상 합성)."""
    parts: list[str] = []
    title = (raw.get("pblancNm") or "").strip()
    if title:
        parts.append(title)
    lclas = raw.get("pldirSportRealmLclasCodeNm")
    mlsfc = raw.get("pldirSportRealmMlsfcCodeNm")
    realm = " ".join(x for x in (lclas, mlsfc) if x)
    if realm:
        parts.append(f"[{realm.strip()}]")
    trget = raw.get("trgetNm")
    if trget:
        parts.append(f"대상: {str(trget).strip()}")
    return " ".join(parts) if parts else None


class BizinfoCollector(BaseCollector):
    """기업마당 지원사업 수집기 (requires_detail=True).

    list 단계는 임베딩 보류 → enrich_detail에서 본문 추출 후 임베딩(중복 방지).
    client / session_factory 주입 가능(테스트 용이성).
    """

    source_code = SOURCE_CODE
    requires_detail = True

    def __init__(
        self,
        client: BizinfoClient | None = None,
        session_factory=None,
    ) -> None:
        if client is None:
            self.client = BizinfoClient(
                settings.bizinfo_base_url,
                settings.bizinfo_crtfc_key,
            )
        else:
            self.client = client

        if session_factory is not None:
            self._session_factory = session_factory

    def iter_pages(self, window: _Window) -> Iterator[list[dict]]:
        """역순 cutoff 페이지네이션 (서버 날짜필터 없음, 등록일 최신순).

        종료조건(collector-base-bizinfo §3.2):
          1. 빈 페이지
          2. 페이지 전체가 creatPnttm < window.begin (윈도우 이전)
          3. 이미 본 것으로 추정되는 연속 seen_streak 초과 — 보수적으로 cutoff와 병행
          4. MAX_PAGES 가드
        """
        page_unit = settings.bizinfo_page_unit
        for page in count(1):
            items = self.client.fetch(page_index=page, page_unit=page_unit)
            if not items:
                return

            yield items

            # cutoff: 페이지 내 모든 항목이 윈도우 시작 이전이면 종료(이후 페이지는 더 과거)
            posted = [parse_kst(it.get("creatPnttm")) for it in items]
            if posted and all(p is not None and p < window.begin for p in posted):
                logger.debug("bizinfo: cutoff (page %d 전체가 window.begin 이전)", page)
                return

            if page >= settings.ingest_max_pages:
                logger.warning("bizinfo: MAX_PAGES(%d) 초과", settings.ingest_max_pages)
                return

    def parse_item(self, raw: dict) -> OpportunityDTO:
        """raw item → OpportunityDTO (list 단계, 예산은 상세에서 보강).

        필드명 검증 완료. content_hash는 본문 미포함(stub) → enrich 후 재계산됨.
        """
        title = (raw.get("pblancNm") or "").strip()
        agency = raw.get("jrsdInsttNm") or raw.get("excInsttNm")  # 소관 우선
        category = raw.get("pldirSportRealmLclasCodeNm")

        # reqstBeginEndDe: 'YYYY-MM-DD ~ YYYY-MM-DD' 범위 또는 비정형 → 분리
        application_start_at, deadline = split_reqst_period(raw.get("reqstBeginEndDe"))

        posted_at = parse_kst(raw.get("creatPnttm"))
        description = _build_stub_desc(raw)

        # 예산은 list에 없음 → None (enrich_detail에서 채움)
        content_hash = sha256_norm(title, agency, deadline, None, description)

        return OpportunityDTO(
            source=self.source_code,
            source_uid=str(raw.get("pblancId") or ""),
            source_ord=None,  # 기업마당은 차수 개념 없음
            title=title,
            agency=agency,
            category=category,
            budget_raw=None,
            budget_amount=None,
            posted_at=posted_at,
            application_start_at=application_start_at,
            deadline=deadline,
            detail_url=raw.get("pblancUrl"),  # 절대경로(검증)
            description=description,
            raw_json=raw,
            status=derive_status(deadline),
            content_hash=content_hash,
        )
