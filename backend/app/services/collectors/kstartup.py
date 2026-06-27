"""K-Startup 창업 지원사업 공고 수집기 (P0 3순위).

정본: docs/04-architecture/collector-kstartup-ntis.md §1 / p0-source-spec.md §3.
dataset: data.go.kr 15125364 (창업진흥원 K-Startup 조회서비스).
인증: data.go.kr serviceKey (KSTARTUP_SERVICE_KEY, 없으면 NARAJANGTER_SERVICE_KEY 폴백).
requires_detail=False — 목록 필드만으로 임베딩 대상.

상태(2026-06-22, 서비스설계서 v2.0 기준):
  - 오퍼레이션 `getAnnouncementInformation01` + **필드명 공식 문서로 확정**:
    title=biz_pbanc_nm, agency=pbanc_ntrp_nm, category=supt_biz_clsfc, region=supt_regin,
    bgn/end=pbanc_rcpt_bgng_dt/pbanc_rcpt_end_dt('YYYY-MM-DD HH:MM:SS'), url=detl_pg_url,
    source_uid=pbanc_sn. (parse_kst가 출력 일시·YYYYMMDD 모두 수용.)
  - 응답 envelope: 문서 예시가 `<items><item>`(표준 스타일) — JSON 정확 형태는 미확인 →
    `KStartupClient`가 평면(data)·단순(items.item)·표준(response.body.items) 모두 방어.
  - ⚠️ **남은 블로커: 403 = B552735 활용신청 미승인.** data.go.kr 마이페이지에서
    '창업진흥원_K-Startup…조회서비스' 승인상태 확인(나라장터와 동일 계정·키). 승인 후
    1회 라이브 확인 → COLLECTORS 등록.
"""
from __future__ import annotations

import logging
from collections.abc import Iterator
from itertools import count

from app.core.config import settings
from app.services.collectors.base import BaseCollector, OpportunityDTO, _Window
from app.services.collectors.client import KStartupClient
from app.services.collectors.normalize import (
    derive_status,
    parse_kst,
    sha256_norm,
)

logger = logging.getLogger(__name__)

_PER_PAGE = 100
_DATE_FMT = "%Y%m%d"  # window 로그용(서버 필터 미지원 — cond 구문 미적용)
# 응답은 pbanc_sn DESC(최신순). 전체 ~29k이므로 최근 N페이지만 수집(open은 최신측에 분포).
_MAX_PAGES = 5  # 100*5 = 최근 500건

# ⚠️ TODO(검증): 오퍼레이션 suffix 확인(공식 명세).
# nidview.k-startup.go.kr 예시: getAnnouncementInformation01
# 공공데이터포털 15125364: getAnnouncementInformation (suffix 없을 수도 있음)
_OPERATION = "getAnnouncementInformation01"


def _service_key() -> str:
    """K-Startup 키: kstartup_service_key → narajangter_service_key 폴백."""
    return settings.kstartup_service_key or settings.narajangter_service_key


def _build_description(raw: dict) -> str | None:
    """MVP description 합성: 사업공고명 / 기관 / 분류 / 지역.

    임베딩 텍스트 품질 보강용. content_hash 입력이므로 규칙 변경 시 전 레코드 재임베딩됨.
    TODO(검증): 필드명 실측 확인 후 필드 보강.
    """
    parts: list[str] = []
    title = (raw.get("biz_pbanc_nm") or "").strip()  # TODO(검증)
    if title:
        parts.append(title)
    agency = raw.get("pbanc_ntrp_nm")  # TODO(검증)
    if agency:
        parts.append(str(agency).strip())
    category = raw.get("supt_biz_clsfc")  # TODO(검증)
    if category:
        parts.append(f"[{str(category).strip()}]")
    region = raw.get("supt_regin")  # TODO(검증)
    if region:
        parts.append(f"지역: {str(region).strip()}")
    return " / ".join(parts) if parts else None


class KStartupCollector(BaseCollector):
    """K-Startup 창업 지원사업 공고 수집기.

    client / session_factory를 생성자에서 주입받아 테스트 용이성 확보.
    기본값은 실제 구현(settings에서 읽음).

    ⚠️ TODO(검증): 응답 envelope(표준 vs 평면형), 날짜필터 파라미터명, 페이징 파라미터명,
      응답 필드명(공고 일련번호 키 등) 실측 확인 필요.
    """

    source_code = "kstartup"
    requires_detail = False

    def __init__(
        self,
        client: KStartupClient | None = None,
        session_factory=None,
    ) -> None:
        if client is None:
            # B552735 신형 평면형 응답 — 전용 클라이언트(KStartupClient).
            self.client = KStartupClient(
                settings.kstartup_base_url,
                _service_key(),
            )
        else:
            self.client = client

        if session_factory is not None:
            self._session_factory = session_factory

    def iter_pages(self, window: _Window) -> Iterator[list[dict]]:
        """서버 날짜필터 + page/perPage 페이지네이션.

        종료 조건:
          1. items < perPage (마지막 페이지)
          2. totalCount 도달
          3. page >= MAX_PAGES (안전 상한)

        ⚠️ TODO(검증): 날짜필터 파라미터명(pbanc_rcpt_bgng_dt/pbanc_rcpt_end_dt) 확인.
          페이징 파라미터명(page/perPage vs pageNo/numOfRows) 확인.
        """
        # B552735 신형은 cond[field::op]=val 필터 구문 — 평문 날짜 params는 미지원/무시될 수
        # 있어 제거. 키 승인 후 cond 구문으로 서버 날짜필터 확정. 현재는 페이지네이션 + 멱등 UPSERT.
        bgn_ymd = window.begin.strftime(_DATE_FMT)
        end_ymd = window.end.strftime(_DATE_FMT)
        logger.debug("kstartup window=%s~%s (서버 날짜필터 미적용 — 키 승인 후 cond 구문)", bgn_ymd, end_ymd)

        fetched_total = 0
        for page in count(1):
            payload = self.client.get(_OPERATION, {
                "page": page,
                "perPage": _PER_PAGE,
                "returnType": "json",
            })
            items = self.client.items(payload)
            total_count = self.client.total_count(payload)

            if not items:
                break

            yield items
            fetched_total += len(items)

            if len(items) < _PER_PAGE:
                break

            if total_count is not None and fetched_total >= total_count:
                break

            if page >= _MAX_PAGES:
                logger.debug("kstartup: 최근 %d페이지(%d건) 수집 — 종료", _MAX_PAGES, fetched_total)
                break

    def parse_item(self, raw: dict) -> OpportunityDTO:
        """raw item dict → OpportunityDTO.

        필드 매핑 기준: collector-kstartup-ntis.md §1.2 / p0-source-spec.md §3.
        모든 필드는 .get() 방어 접근.
        ⚠️ TODO(검증): 공고 일련번호 키명, 모든 응답 필드명 실측 확인 필요.
        """
        # ── 기본 필드 ─────────────────────────────────────────────────
        title: str = (raw.get("biz_pbanc_nm") or "").strip()  # TODO(검증)
        agency: str | None = raw.get("pbanc_ntrp_nm")  # TODO(검증)
        category: str | None = raw.get("supt_biz_clsfc")  # TODO(검증)
        region: str | None = raw.get("supt_regin")  # TODO(검증)

        # ── 일시 ──────────────────────────────────────────────────────
        # p0-source-spec §3 정정: pbanc_rcpt_bgng_dt → application_start_at
        # (posted_at 아님 — db-schema §5 통합 매핑 정정)
        application_start_at = parse_kst(raw.get("pbanc_rcpt_bgng_dt"))  # TODO(검증)
        deadline = parse_kst(raw.get("pbanc_rcpt_end_dt"))  # TODO(검증)

        # posted_at: 등록일 — K-Startup 목록에 없을 수 있음 → NULL 허용
        # TODO(검증): 등록일 필드명 확인(예: 'reg_dt', 'creat_dt' 등)
        posted_at = parse_kst(raw.get("reg_dt") or raw.get("creat_dt"))  # TODO(검증)

        # ── 식별자 ────────────────────────────────────────────────────
        # TODO(검증): 공고 일련번호 키명 확인
        # 후보: 'pbancSn', 'pbanc_sn', 'announcement_id', 'biz_pbanc_no' 등
        source_uid: str = str(
            raw.get("pbancSn")
            or raw.get("pbanc_sn")
            or raw.get("announcement_id")
            or raw.get("biz_pbanc_no")
            or ""
        )

        # ── description ────────────────────────────────────────────────
        description = _build_description(raw)

        # ── content_hash ───────────────────────────────────────────────
        # K-Startup 목록에 예산 없음(requires_detail=False이나 예산 미제공)
        content_hash = sha256_norm(title, agency, deadline, None, description)

        return OpportunityDTO(
            source=self.source_code,
            source_uid=source_uid,
            source_ord=None,  # K-Startup 차수 개념 없음
            title=title,
            agency=agency,
            category=category,
            region=region,
            budget_raw=None,
            budget_amount=None,
            posted_at=posted_at,
            application_start_at=application_start_at,
            deadline=deadline,
            detail_url=raw.get("detl_pg_url"),  # TODO(검증)
            description=description,
            raw_json=raw,
            status=derive_status(deadline),
            content_hash=content_hash,
        )
