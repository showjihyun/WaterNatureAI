"""나라장터 입찰공고 수집기 (P0 1순위).

정본: collector-narajangter.md.
업무유형 4종(물품/용역/공사/외자)을 순회.
source_uid = bidNtceNo (차수 미포함), source_ord = bidNtceOrd.

필드명 검증 완료(2026-06, 15129394 공식 OpenAPI 스키마 + 동작 클라이언트 교차확인):
  bidNtceNo(입찰공고번호)·bidNtceOrd(차수)·bidNtceNm(공고명)·ntceInsttNm(공고기관)·
  dminsttNm(수요기관)·bidNtceDt(공고일시)·bidClseDt(마감일시)·
  presmptPrce(추정가격)·asignBdgtAmt(배정예산)·bidNtceDtlUrl(상세URL) 모두 확인.
  응답 일시 포맷 = 'yyyy-MM-dd HH:mm:ss' (요청 inqryBgnDt/EndDt만 'yyyyMMddHHmm').
  참고: 동일 item에 bidBeginDt(입찰개시)·opengDt(개찰) 필드도 존재(현재 미사용).
"""
from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from itertools import count

from app.core.config import settings
from app.services.collectors.base import BaseCollector, OpportunityDTO, _Window
from app.services.collectors.client import DataGoKrClient
from app.services.collectors.normalize import (
    derive_status,
    parse_kst,
    parse_won,
    sha256_norm,
)

logger = logging.getLogger(__name__)

# (오퍼레이션 이름, 업무유형 category 레이블)
OPS: list[tuple[str, str]] = [
    ("getBidPblancListInfoThng", "물품"),
    ("getBidPblancListInfoServc", "용역"),
    ("getBidPblancListInfoCnstwk", "공사"),
    ("getBidPblancListInfoFrgcpt", "외자"),
]

_FMT = "%Y%m%d%H%M"   # inqryBgnDt / inqryEndDt 포맷
# data.go.kr 나라장터 list API는 페이지 크기 상한 100.
# numOfRows>100이면 응답이 10건으로 degrade되어, 종료조건(len<numOfRows) 오판으로 1페이지만 수집됨.
# 100이 안전 최대값.
_NUM_OF_ROWS = 100


# 시/도 추출(지역제한 입찰의 기관명·현장지역명 등에서).
_SIDO = re.compile(
    r"(서울|부산|대구|인천|광주|대전|울산|세종|경기|강원|충북|충남|전북|전남|경북|경남|제주)"
)


def _parse_region(raw: dict) -> str | None:
    """지역 추출 — 공사현장 지역(cnstrtsiteRgnNm) 우선, 없으면 지역제한 입찰의 기관 시/도.

    대부분 입찰은 전국(지역제한 없음) → None(=제한없음). 매칭에서 None은 중립 처리.
    """
    site = (raw.get("cnstrtsiteRgnNm") or "").strip()
    if site:
        m = _SIDO.search(site)
        return m.group(1) if m else site
    if (raw.get("rgnLmtBidLocplcJdgmBssNm") or "").strip():
        m = _SIDO.search(str(raw.get("ntceInsttNm") or raw.get("dminsttNm") or ""))
        if m:
            return m.group(1)
    return None


def _build_description(raw: dict) -> str | None:
    """목록 API의 풍부한 필드를 조합한 구조화 요약(상세페이지 표시 + 임베딩 신호 보강).

    상세 본문(규격서)은 첨부파일(PDF/HWP)이라 목록 API에 없음 — 대신 분류·수량·방식·납품·
    지역제한·첨부파일명 등 목록 API가 주는 102개 필드 중 의미 있는 것으로 요약을 구성한다.
    content_hash 입력 필드라 규칙 변경 시 전 레코드 재임베딩됨(의도적: 더 풍부한 벡터).
    """
    title = (raw.get("bidNtceNm") or "").strip()
    agency = raw.get("ntceInsttNm") or raw.get("dminsttNm")
    category = raw.get("_category")

    parts: list[str] = []
    head = f"[{category}] {title}" if category and title else title
    if head:
        parts.append(head)
    if agency:
        parts.append(str(agency).strip())

    # 분류명(상세품목분류 > 품목분류 > 사업구분)
    clsfc = (
        raw.get("dtilPrdctClsfcNoNm") or raw.get("prdctClsfcNoNm") or raw.get("bsnsDivNm")
    )
    if clsfc:
        parts.append(f"분류: {str(clsfc).strip()}")

    # 수량·단위(물품)
    qty = str(raw.get("prdctQty") or "").strip()
    if qty and qty != "0":
        unit = str(raw.get("prdctUnit") or "").strip()
        parts.append(f"수량: {qty}{(' ' + unit) if unit else ''}")

    # 계약/입찰 방식
    methods = [str(raw.get(k) or "").strip() for k in ("cntrctCnclsMthdNm", "bidMethdNm")]
    methods = [m for m in methods if m and m not in ("없음", "(없음)")]
    if methods:
        parts.append("방식: " + " · ".join(methods))

    # 납품기한(물품)
    dlvr = str(raw.get("dlvrDaynum") or "").strip()
    if dlvr and dlvr != "0":
        parts.append(f"납품기한: {dlvr}일")

    # 지역제한(있으면)
    rgnlmt = (raw.get("rgnLmtBidLocplcJdgmBssNm") or "").strip()
    if rgnlmt:
        parts.append(f"지역제한: {rgnlmt}")

    # 첨부파일명(공고문·규격서 등 — 내용 힌트로 임베딩 신호 보강)
    files = [str(raw.get(f"ntceSpecFileNm{i}") or "").strip() for i in (1, 2, 3)]
    files = [f for f in files if f]
    if files:
        parts.append("첨부: " + ", ".join(files))

    return " / ".join(parts) if parts else None


class NarajangterCollector(BaseCollector):
    """나라장터 입찰공고 수집기.

    client / session_factory를 생성자에서 주입받아 테스트 용이성 확보.
    기본값은 실제 구현(settings에서 읽음).
    """

    source_code = "narajangter"
    requires_detail = False

    def __init__(
        self,
        client: DataGoKrClient | None = None,
        session_factory=None,
    ) -> None:
        if client is None:
            self.client = DataGoKrClient(
                settings.narajangter_base_url,
                settings.narajangter_service_key,
            )
        else:
            self.client = client

        # session_factory 주입 지원 (BaseCollector._session_factory 참조)
        if session_factory is not None:
            self._session_factory = session_factory

        self._category: str = "물품"  # iter_pages 진행 중 현재 업무유형 추적

    def iter_pages(self, window: _Window) -> Iterator[list[dict]]:
        """4개 업무유형을 순회하며 페이지 단위로 raw item 리스트를 yield.

        페이지 종료 조건(collector-narajangter.md §5):
        1. len(items) < numOfRows (마지막 페이지)
        2. totalCount 도달
        3. page >= MAX_PAGES (안전 상한)
        """
        bgn = window.begin.strftime(_FMT)
        end = window.end.strftime(_FMT)

        for op, category in OPS:
            self._category = category
            fetched_total = 0

            for page in count(1):
                payload = self.client.get(op, {
                    "inqryDiv": 1,
                    "inqryBgnDt": bgn,
                    "inqryEndDt": end,
                    "pageNo": page,
                    "numOfRows": _NUM_OF_ROWS,
                })
                items = self.client.items(payload)
                total_count = self.client.total_count(payload)

                if not items:
                    break  # NODATA 또는 빈 페이지

                # category를 각 raw item에 주입 (parse_item이 참조)
                for it in items:
                    it["_category"] = category

                yield items
                fetched_total += len(items)

                # 종료 조건 1: 마지막 페이지 (items < numOfRows)
                if len(items) < _NUM_OF_ROWS:
                    break

                # 종료 조건 2: totalCount 도달
                if total_count is not None and fetched_total >= total_count:
                    break

                # 종료 조건 3: MAX_PAGES 안전 상한 초과
                if page >= settings.ingest_max_pages:
                    logger.warning(
                        "narajangter: MAX_PAGES(%d) 초과 — op=%s, fetched=%d",
                        settings.ingest_max_pages, op, fetched_total,
                    )
                    break

    def parse_item(self, raw: dict) -> OpportunityDTO:
        """raw item dict → OpportunityDTO.

        필드 매핑 기준: collector-narajangter.md §6 / db-schema-opportunities §6.
        모든 필드는 .get() 방어 접근. 필드명은 15129394 기준 검증 완료(헤더 주석 참고).
        """
        # ── 기본 필드 (필드명 검증 완료) ───────────────────────────
        title: str = (raw.get("bidNtceNm") or "").strip()
        agency: str | None = (
            raw.get("ntceInsttNm") or raw.get("dminsttNm")  # 공고기관 우선, 수요기관 보조
        )
        category: str | None = raw.get("_category") or self._category

        # ── 예산 (검증: presmptPrce 추정가격 / asignBdgtAmt 배정예산) ──
        # 우선순위 presmptPrce → asignBdgtAmt (db-schema §6). 물품/용역은 추정가격이
        # 더 흔히 채워지며, 미제공 시 배정예산으로 폴백. 둘 다 숫자 문자열.
        budget_raw: str | None = (
            raw.get("presmptPrce") or raw.get("asignBdgtAmt")
        )
        budget_amount: int | None = parse_won(budget_raw)

        # ── 일시 (검증 완료: 'yyyy-MM-dd HH:mm:ss', parse_kst가 흡수) ──
        posted_at = parse_kst(raw.get("bidNtceDt"))
        deadline = parse_kst(raw.get("bidClseDt"))

        # ── 식별 (필드명 검증 완료) ────────────────────────────────
        # source_uid: bidNtceNo (차수 미포함 — db-schema §1 결정 #2)
        source_uid: str = str(raw.get("bidNtceNo") or "")

        # source_ord: bidNtceOrd (int 변환, 없으면 None)
        raw_ord = raw.get("bidNtceOrd")
        source_ord: int | None = None
        if raw_ord is not None:
            try:
                source_ord = int(raw_ord)
            except (ValueError, TypeError):
                logger.warning("narajangter: bidNtceOrd 변환 실패 — value=%r", raw_ord)

        # ── description (목록 API 풍부 필드 구조화 요약) ───────────
        description = _build_description(raw)
        region = _parse_region(raw)

        # ── content_hash: sha256(title|agency|deadline|budget_amount|description)
        # db-schema §6 / collector-narajangter §6 SSOT
        content_hash = sha256_norm(title, agency, deadline, budget_amount, description)

        return OpportunityDTO(
            source=self.source_code,
            source_uid=source_uid,
            source_ord=source_ord,
            title=title,
            agency=agency,
            category=category,
            region=region,
            budget_raw=budget_raw,
            budget_amount=budget_amount,
            posted_at=posted_at,
            deadline=deadline,
            detail_url=raw.get("bidNtceDtlUrl"),                   # 검증 완료(상세 URL)
            description=description,
            raw_json=raw,
            status=derive_status(deadline),
            content_hash=content_hash,
        )
