"""NTIS 과학기술정보통신부 사업공고 수집기 (P0 4순위).

정본: docs/06-data api ref/OpenApi활용가이드_과학기술정보통신부_사업공고_v1.0.docx
      (공식 명세, 2026-06-23 반영) / collector-kstartup-ntis.md §2.
dataset: data.go.kr 15074634 (과학기술정보통신부_사업공고, provider 1721000).
endpoint: http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList
인증: data.go.kr serviceKey (NTIS_SERVICE_KEY, 없으면 NARAJANGTER_SERVICE_KEY 폴백).
requires_detail=False.

공식 명세 확정(이전 추측 필드명 폐기):
  - 응답 envelope: 표준 `response.body.items.item[]` (DataGoKrClient 그대로 사용).
  - 필드: subject=제목, viewUrl=상세URL, deptName=담당부서, pressDt=게시일(YYYY-MM-DD),
    managerName/managerTel=담당자, files[].fileName/fileUrl=첨부. **마감·예산·분류·지역·ID 없음.**
  - 페이징: pageNo / numOfRows(**고정 10**) / returnType(json).
  - 정렬: pressDt DESC(최신순). totalCount는 body.items 내부.

⚠️ 마감(deadline) 부재 → derive_status는 항상 'unknown'이 되어 매칭(status='open')에서
  영구 제외됨. 따라서 **게시일 기준 최근(_OPEN_WINDOW_DAYS) = 'open'** 으로 상태를 부여한다.
  실제 접수마감은 첨부 공고문(.hwp)에 있음 — 상세 파싱은 범위 밖(상세 링크 제공으로 갈음).
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from itertools import count
from urllib.parse import parse_qs, urlparse

from app.core.config import settings
from app.services.collectors.base import BaseCollector, OpportunityDTO, _Window
from app.services.collectors.client import NtisClient
from app.services.collectors.normalize import parse_kst, sha256_norm

logger = logging.getLogger(__name__)

_NUM_OF_ROWS = 10  # 공식 명세상 페이지당 결과 수 고정(10).
_OPERATION = "businessAnnouncMentList"  # 공식 명세 확정.
# 게시일 기준 'open' 윈도우. R&D 공고 접수기간(보통 수주)을 보수적으로 포괄.
_OPEN_WINDOW_DAYS = 60
# 최신순 수집 안전 상한(컷오프가 보통 더 먼저 종료). 10건/페이지.
_MAX_PAGES = 50
_MINISTRY = "과학기술정보통신부"


def _service_key() -> str:
    """NTIS 키: ntis_service_key → narajangter_service_key 폴백."""
    return settings.ntis_service_key or settings.narajangter_service_key


def _extract_source_uid(raw: dict) -> str:
    """공고 식별자 — 응답에 ID 필드가 없어 viewUrl의 nttSeqNo로 대체.

    viewUrl 예: https://www.msit.go.kr/bbs/view.do?...&nttSeqNo=3176928
    nttSeqNo 없으면 subject+pressDt 해시로 안정 식별자 생성.
    """
    view_url = raw.get("viewUrl") or ""
    try:
        qs = parse_qs(urlparse(view_url).query)
        ntt = qs.get("nttSeqNo", [None])[0]
        if ntt:
            return str(ntt)
    except (ValueError, TypeError):
        pass
    # 폴백: 안정 해시(제목+게시일).
    basis = f"{raw.get('subject', '')}|{raw.get('pressDt', '')}"
    return sha256_norm(basis)[:24]


def _agency(raw: dict) -> str:
    """발주처 = 과학기술정보통신부 + 담당부서(있으면)."""
    dept = (raw.get("deptName") or "").strip()
    return f"{_MINISTRY} {dept}".strip() if dept else _MINISTRY


def _build_description(raw: dict) -> str | None:
    """description 합성: 제목 / 부처·부서 / 담당자. 임베딩 텍스트 품질 보강용."""
    parts: list[str] = []
    subject = (raw.get("subject") or "").strip()
    if subject:
        parts.append(subject)
    parts.append(_agency(raw))
    manager = (raw.get("managerName") or "").strip()
    if manager:
        parts.append(f"담당: {manager}")
    return " / ".join(parts) if parts else None


def _status_from_pressdt(posted_at: datetime | None) -> str:
    """게시일 기준 상태. 최근(_OPEN_WINDOW_DAYS 이내)=open, 그 외=closed.

    NTIS 목록에 마감이 없어 derive_status(None)='unknown'이면 매칭에서 빠지므로,
    게시일 신선도로 'open'을 부여(접수마감 정확값은 첨부 공고문에 존재).
    """
    if posted_at is None:
        return "open"  # 게시일 불명(명세상 필수라 드묾) → 보수적으로 노출.
    age = datetime.now(timezone.utc) - posted_at
    return "open" if age <= timedelta(days=_OPEN_WINDOW_DAYS) else "closed"


class NtisCollector(BaseCollector):
    """NTIS 과학기술정보통신부 사업공고 수집기(공식 명세 반영).

    client / session_factory를 생성자에서 주입받아 테스트 용이성 확보.
    """

    source_code = "ntis"
    requires_detail = False

    def __init__(
        self,
        client: NtisClient | None = None,
        session_factory=None,
    ) -> None:
        if client is None:
            self.client = NtisClient(settings.ntis_base_url, _service_key())
        else:
            self.client = client

        if session_factory is not None:
            self._session_factory = session_factory

    def iter_pages(self, window: _Window) -> Iterator[list[dict]]:
        """pageNo/numOfRows 페이지네이션 + 게시일 컷오프(최신순 정렬 전제).

        종료 조건:
          1. items 없음
          2. items < numOfRows (마지막 페이지)
          3. 페이지 전체가 open 윈도우보다 과거(이후 페이지는 모두 더 과거)
          4. page >= _MAX_PAGES (안전 상한)
        """
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=_OPEN_WINDOW_DAYS)
        for page in count(1):
            payload = self.client.get(_OPERATION, {
                "pageNo": page,
                "numOfRows": _NUM_OF_ROWS,
                "returnType": "json",
            })
            items = self.client.items(payload)
            if not items:
                break

            yield items

            if len(items) < _NUM_OF_ROWS:
                break

            posted_dates = [parse_kst(it.get("pressDt")) for it in items]
            if posted_dates and all(
                p is not None and p < cutoff_dt for p in posted_dates
            ):
                logger.debug("ntis: cutoff (page %d 전체가 open 윈도우 밖)", page)
                break

            if page >= _MAX_PAGES:
                logger.warning("ntis: MAX_PAGES(%d) 도달", _MAX_PAGES)
                break

    def parse_item(self, raw: dict) -> OpportunityDTO:
        """raw item dict → OpportunityDTO. 공식 명세 필드 매핑.

        마감·예산·분류·지역 미제공 → None. 상태는 게시일 신선도 기반.
        """
        title: str = (raw.get("subject") or "").strip()
        agency: str = _agency(raw)
        posted_at = parse_kst(raw.get("pressDt"))
        source_uid: str = _extract_source_uid(raw)
        description = _build_description(raw)
        status = _status_from_pressdt(posted_at)

        # 마감·예산 미제공 → content_hash는 title|agency|None|None|description.
        content_hash = sha256_norm(title, agency, None, None, description)

        return OpportunityDTO(
            source=self.source_code,
            source_uid=source_uid,
            source_ord=None,
            title=title,
            agency=agency,
            category=None,      # 목록 미제공
            region=None,        # 목록 미제공
            budget_raw=None,
            budget_amount=None,
            posted_at=posted_at,
            application_start_at=None,
            deadline=None,      # 목록 미제공(첨부 공고문에 존재)
            detail_url=raw.get("viewUrl"),
            description=description,
            raw_json=raw,
            status=status,      # 게시일 신선도 기반(derive_status 미사용)
            content_hash=content_hash,
        )
