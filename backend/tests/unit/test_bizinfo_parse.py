"""단위 테스트: BizinfoCollector.parse_item + BizinfoClient.items.

라이브 검증된 기업마당 응답 필드/값 기반 fixture (DB/HTTP 없음).
정본: collector-base-bizinfo.md §3.3 / docs/06 검증.
"""
from __future__ import annotations

import pytest

from app.services.collectors.bizinfo import BizinfoClient, BizinfoCollector
from app.services.collectors.normalize import KST, sha256_norm


class _DummyClient:
    def fetch(self, page_index, page_unit):  # noqa: ARG002
        return []

    @staticmethod
    def items(payload):
        return BizinfoClient.items(payload)


@pytest.fixture()
def collector() -> BizinfoCollector:
    return BizinfoCollector(client=_DummyClient())  # type: ignore[arg-type]


@pytest.fixture()
def bizinfo_item() -> dict:
    """라이브 확인된 기업마당 목록 item (대표 필드)."""
    return {
        "pblancId": "PBLN_000000000123405",
        "pblancNm": "2026년 우주항공 개념설계 연구개발 지원사업",
        "jrsdInsttNm": "과학기술정보통신부",
        "excInsttNm": "우주항공청",
        "reqstBeginEndDe": "2026-06-15 ~ 2026-06-29",
        "creatPnttm": "2026-06-19 15:22:27",
        "pldirSportRealmLclasCodeNm": "기술",
        "pldirSportRealmMlsfcCodeNm": "공동기술개발",
        "trgetNm": "중소기업",
        "hashtags": "우주,항공,R&D",
        "pblancUrl": (
            "https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do"
            "?pblancId=PBLN_000000000123405"
        ),
    }


# ── BizinfoClient.items (envelope 파싱) ───────────────────────────────────

class TestBizinfoClientItems:
    def test_json_array(self, bizinfo_item):
        payload = {"jsonArray": [bizinfo_item, bizinfo_item]}
        assert len(BizinfoClient.items(payload)) == 2

    def test_empty_json_array(self):
        assert BizinfoClient.items({"jsonArray": []}) == []

    def test_missing_json_array(self):
        assert BizinfoClient.items({}) == []

    def test_req_err_shape_has_no_items(self):
        # reqErr는 fetch()에서 예외 처리 — items()는 단순히 빈 리스트
        assert BizinfoClient.items({"reqErr": "존재하지 않는 인증키 입니다."}) == []

    def test_flat_list_fallback(self, bizinfo_item):
        assert BizinfoClient.items([bizinfo_item]) == [bizinfo_item]


# ── parse_item ────────────────────────────────────────────────────────────

class TestBizinfoParseItem:
    def test_source(self, collector, bizinfo_item):
        assert collector.parse_item(bizinfo_item).source == "bizinfo"

    def test_source_uid_is_pblanc_id(self, collector, bizinfo_item):
        assert collector.parse_item(bizinfo_item).source_uid == "PBLN_000000000123405"

    def test_source_ord_none(self, collector, bizinfo_item):
        """기업마당은 차수 개념 없음 → None."""
        assert collector.parse_item(bizinfo_item).source_ord is None

    def test_title(self, collector, bizinfo_item):
        dto = collector.parse_item(bizinfo_item)
        assert dto.title == "2026년 우주항공 개념설계 연구개발 지원사업"

    def test_agency_prefers_jrsd(self, collector, bizinfo_item):
        """소관기관(jrsdInsttNm) 우선."""
        assert collector.parse_item(bizinfo_item).agency == "과학기술정보통신부"

    def test_agency_fallback_to_exc(self, collector, bizinfo_item):
        bizinfo_item["jrsdInsttNm"] = None
        assert collector.parse_item(bizinfo_item).agency == "우주항공청"

    def test_category(self, collector, bizinfo_item):
        assert collector.parse_item(bizinfo_item).category == "기술"

    def test_posted_at_kst(self, collector, bizinfo_item):
        dto = collector.parse_item(bizinfo_item)
        assert dto.posted_at is not None
        assert dto.posted_at.tzinfo == KST
        assert dto.posted_at.year == 2026 and dto.posted_at.hour == 15

    def test_application_period_split(self, collector, bizinfo_item):
        """reqstBeginEndDe 범위 → application_start_at / deadline 분리."""
        dto = collector.parse_item(bizinfo_item)
        assert dto.application_start_at is not None and dto.application_start_at.day == 15
        assert dto.deadline is not None and dto.deadline.day == 29

    def test_detail_url_absolute(self, collector, bizinfo_item):
        dto = collector.parse_item(bizinfo_item)
        assert dto.detail_url.startswith("https://www.bizinfo.go.kr/")

    def test_budget_none_at_list_stage(self, collector, bizinfo_item):
        """예산은 목록에 없음 → list 단계 None (enrich에서 채움)."""
        dto = collector.parse_item(bizinfo_item)
        assert dto.budget_raw is None
        assert dto.budget_amount is None

    def test_content_hash_excludes_budget(self, collector, bizinfo_item):
        """list 단계 hash = sha256(title|agency|deadline|None|description)."""
        dto = collector.parse_item(bizinfo_item)
        expected = sha256_norm(
            dto.title, dto.agency, dto.deadline, None, dto.description
        )
        assert dto.content_hash == expected

    def test_status_open_future(self, collector, bizinfo_item):
        assert collector.parse_item(bizinfo_item).status == "open"

    def test_raw_json_preserved(self, collector, bizinfo_item):
        dto = collector.parse_item(bizinfo_item)
        assert dto.raw_json["pblancId"] == "PBLN_000000000123405"


# ── 비정형 신청기간 (라이브 실측) ─────────────────────────────────────────

class TestBizinfoNonstandardPeriod:
    @pytest.mark.parametrize(
        "value", ["예산 소진시까지", "상시 접수", "모집 완료시", "선착순 접수"]
    )
    def test_rolling_period_unknown_status(self, collector, bizinfo_item, value):
        """비정형 신청기간 → deadline None, status unknown, 레코드 보존."""
        bizinfo_item["reqstBeginEndDe"] = value
        dto = collector.parse_item(bizinfo_item)
        assert dto.deadline is None
        assert dto.status == "unknown"
        assert dto.source_uid == "PBLN_000000000123405"  # 레코드는 보존


# ── 방어 ──────────────────────────────────────────────────────────────────

class TestBizinfoDefensive:
    def test_minimal_item(self, collector):
        dto = collector.parse_item({"pblancId": "PBLN_X", "pblancNm": "최소"})
        assert dto.source_uid == "PBLN_X"
        assert dto.title == "최소"
        assert dto.deadline is None
        assert dto.status == "unknown"

    def test_missing_pblanc_id(self, collector):
        assert collector.parse_item({"pblancNm": "x"}).source_uid == ""
