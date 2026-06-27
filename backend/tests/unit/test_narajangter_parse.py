"""단위 테스트: NarajangterCollector.parse_item — DTO 필드 매핑 검증.

현실적인 나라장터 raw item fixture(conftest.py)를 사용.
DB/HTTP 없음. category 주입 포함.
정본: collector-narajangter.md §6 / db-schema §6.
"""
from __future__ import annotations


import pytest

from app.services.collectors.narajangter import (
    NarajangterCollector,
    _build_description,
    _parse_region,
)
from app.services.collectors.normalize import KST, sha256_norm

# 테스트용 더미 client (HTTP 없음)
class _DummyClient:
    def get(self, *a, **kw):
        return {}

    @staticmethod
    def items(payload):
        return []

    @staticmethod
    def total_count(payload):
        return None


@pytest.fixture()
def collector() -> NarajangterCollector:
    return NarajangterCollector(client=_DummyClient())  # type: ignore[arg-type]


# ── 물품 공고 parse_item ─────────────────────────────────────────────────

class TestParseItemThng:
    def test_source_is_narajangter(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.source == "narajangter"

    def test_source_uid_is_bid_ntce_no(self, collector, narajangter_item_thng):
        """source_uid = bidNtceNo (차수 미포함 — db-schema §1 결정 #2)."""
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.source_uid == "20240600123"

    def test_source_ord_is_bid_ntce_ord(self, collector, narajangter_item_thng):
        """source_ord = bidNtceOrd (int 변환)."""
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.source_ord == 0  # "000" → 0

    def test_title_stripped(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.title == "2024년 사무용 PC 구매 입찰공고"

    def test_agency_prefers_ntce_instt_nm(self, collector, narajangter_item_thng):
        """agency = ntceInsttNm 우선 (dminsttNm 보조)."""
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.agency == "서울특별시 강남구청"

    def test_category_injected(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.category == "물품"

    def test_budget_raw_prefers_presmpt_prce(self, collector, narajangter_item_thng):
        """budget_raw = presmptPrce 우선 (15129394: 숫자 문자열)."""
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.budget_raw == "350000000"

    def test_budget_amount_parsed(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.budget_amount == 350_000_000

    def test_posted_at_kst_aware(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.posted_at is not None
        assert dto.posted_at.tzinfo == KST
        assert dto.posted_at.hour == 10

    def test_deadline_kst_aware(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.deadline is not None
        assert dto.deadline.tzinfo == KST
        assert dto.deadline.year == 2026

    def test_detail_url(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.detail_url is not None
        assert "g2b.go.kr" in dto.detail_url

    def test_status_open_future_deadline(self, collector, narajangter_item_thng):
        """미래 마감일 → open."""
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.status == "open"

    def test_content_hash_64_chars(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert len(dto.content_hash) == 64

    def test_content_hash_deterministic(self, collector, narajangter_item_thng):
        """같은 raw → 같은 content_hash."""
        narajangter_item_thng["_category"] = "물품"
        dto1 = collector.parse_item(narajangter_item_thng)
        dto2 = collector.parse_item(narajangter_item_thng)
        assert dto1.content_hash == dto2.content_hash

    def test_content_hash_matches_sha256_norm(self, collector, narajangter_item_thng):
        """content_hash = sha256_norm(title|agency|deadline|budget_amount|description)."""
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        expected = sha256_norm(
            dto.title, dto.agency, dto.deadline, dto.budget_amount, dto.description
        )
        assert dto.content_hash == expected

    def test_raw_json_preserved(self, collector, narajangter_item_thng):
        narajangter_item_thng["_category"] = "물품"
        dto = collector.parse_item(narajangter_item_thng)
        assert dto.raw_json["bidNtceNo"] == "20240600123"


# ── 용역 공고 parse_item ('yyyy-MM-dd HH:mm:ss' 응답 포맷, presmptPrce=None) ──

class TestParseItemServc:
    def test_category_servc(self, collector, narajangter_item_servc):
        narajangter_item_servc["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_servc)
        assert dto.category == "용역"

    def test_source_ord_int_conversion(self, collector, narajangter_item_servc):
        """"001" → source_ord=1."""
        narajangter_item_servc["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_servc)
        assert dto.source_ord == 1

    def test_budget_falls_back_to_assign_bdgt_amt(self, collector, narajangter_item_servc):
        """presmptPrce=None → asignBdgtAmt 폴백."""
        narajangter_item_servc["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_servc)
        assert dto.budget_raw == "120000000"
        assert dto.budget_amount == 120_000_000

    def test_posted_at_response_format(self, collector, narajangter_item_servc):
        """15129394 응답 일시 포맷('yyyy-MM-dd HH:mm:ss') 파싱."""
        narajangter_item_servc["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_servc)
        assert dto.posted_at is not None
        assert dto.posted_at.tzinfo == KST
        assert dto.posted_at.year == 2026
        assert dto.posted_at.hour == 12

    def test_agency_fallback_to_dminstt_nm(self, collector, narajangter_item_servc):
        """ntceInsttNm 있으면 우선, 없으면 dminsttNm."""
        narajangter_item_servc["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_servc)
        # fixture에서 ntceInsttNm="국토교통부", dminsttNm=None
        assert dto.agency == "국토교통부"

    def test_agency_none_when_both_missing(self, collector, narajangter_item_servc):
        narajangter_item_servc["ntceInsttNm"] = None
        narajangter_item_servc["dminsttNm"] = None
        narajangter_item_servc["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_servc)
        assert dto.agency is None


# ── 마감 공고 (closed) ──────────────────────────────────────────────────

class TestParseItemClosed:
    def test_status_closed(self, collector, narajangter_item_closed):
        narajangter_item_closed["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_closed)
        assert dto.status == "closed"

    def test_budget_with_won_suffix(self, collector, narajangter_item_closed):
        """'50,000,000원' → 50000000."""
        narajangter_item_closed["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_closed)
        assert dto.budget_amount == 50_000_000

    def test_no_detail_url(self, collector, narajangter_item_closed):
        narajangter_item_closed["_category"] = "용역"
        dto = collector.parse_item(narajangter_item_closed)
        assert dto.detail_url is None


# ── 정정공고 해시 변경 ───────────────────────────────────────────────────

class TestAmendedNotice:
    def test_hash_changes_when_ord_increments(
        self, collector, narajangter_item_thng
    ):
        """bidNtceOrd 증가 시 내용(title/etc)도 함께 바뀌면 hash가 달라짐.

        hash는 title|agency|deadline|budget_amount|description 기반이므로,
        차수만 바뀌고 나머지가 동일하면 hash는 같다.
        이 케이스는 내용도 함께 변경되는 현실 시나리오를 시뮬레이션.
        """
        # 1차 공고
        raw_v1 = dict(narajangter_item_thng)
        raw_v1["_category"] = "물품"
        raw_v1["bidNtceOrd"] = "000"
        raw_v1["presmptPrce"] = "350,000,000"
        dto_v1 = collector.parse_item(raw_v1)

        # 정정 공고 (차수+예산 변경)
        raw_v2 = dict(narajangter_item_thng)
        raw_v2["_category"] = "물품"
        raw_v2["bidNtceOrd"] = "001"
        raw_v2["presmptPrce"] = "400,000,000"  # 예산 변경
        dto_v2 = collector.parse_item(raw_v2)

        assert dto_v1.source_uid == dto_v2.source_uid  # 같은 source_uid
        assert dto_v1.source_ord == 0
        assert dto_v2.source_ord == 1
        assert dto_v1.content_hash != dto_v2.content_hash  # hash 다름


# ── 결측/방어 케이스 ─────────────────────────────────────────────────────

class TestParseItemDefensive:
    def test_missing_optional_fields_no_exception(self, collector):
        """필수가 아닌 필드가 모두 빠져도 예외 없음."""
        raw = {
            "bidNtceNo": "99999999999",
            "bidNtceNm": "최소 필드 공고",
        }
        dto = collector.parse_item(raw)
        assert dto.source == "narajangter"
        assert dto.title == "최소 필드 공고"
        assert dto.agency is None
        assert dto.budget_amount is None
        assert dto.posted_at is None
        assert dto.deadline is None
        assert dto.status == "unknown"

    def test_source_uid_empty_string(self, collector):
        """bidNtceNo 없으면 source_uid는 빈 문자열."""
        raw = {"bidNtceNm": "테스트"}
        dto = collector.parse_item(raw)
        assert dto.source_uid == ""

    def test_source_ord_none_when_missing(self, collector):
        raw = {"bidNtceNo": "111", "bidNtceNm": "테스트"}
        dto = collector.parse_item(raw)
        assert dto.source_ord is None


# ── enrich(C): 풍부 description + 지역 파싱 ───────────────────────────────


class TestEnrichDescription:
    def test_includes_classification_quantity_method_files(self):
        raw = {
            "_category": "물품",
            "bidNtceNm": "클러스터 서버",
            "ntceInsttNm": "서울대학교산학협력단",
            "dtilPrdctClsfcNoNm": "컴퓨터서버",
            "prdctQty": "2",
            "prdctUnit": "SET",
            "cntrctCnclsMthdNm": "제한경쟁",
            "bidMethdNm": "전자입찰",
            "dlvrDaynum": "60",
            "ntceSpecFileNm1": "입찰공고문.pdf",
            "ntceSpecFileNm2": "구매규격서.pdf",
        }
        d = _build_description(raw)
        assert "[물품] 클러스터 서버 / 서울대학교산학협력단" in d
        assert "분류: 컴퓨터서버" in d
        assert "수량: 2 SET" in d
        assert "방식: 제한경쟁 · 전자입찰" in d
        assert "납품기한: 60일" in d
        assert "첨부: 입찰공고문.pdf, 구매규격서.pdf" in d

    def test_skips_zero_quantity(self):
        raw = {"_category": "용역", "bidNtceNm": "AI 분석 용역", "ntceInsttNm": "기관", "prdctQty": "0"}
        d = _build_description(raw)
        assert "수량" not in d
        assert d.startswith("[용역] AI 분석 용역 / 기관")


class TestParseRegion:
    def test_construction_site_region_normalized(self):
        assert _parse_region({"cnstrtsiteRgnNm": "대구광역시"}) == "대구"

    def test_region_limited_derives_sido_from_agency(self):
        raw = {
            "rgnLmtBidLocplcJdgmBssNm": "본사또는참여지사소재지",
            "ntceInsttNm": "한국농어촌공사 전북지역본부",
        }
        assert _parse_region(raw) == "전북"

    def test_nationwide_returns_none(self):
        assert _parse_region({"ntceInsttNm": "조달청"}) is None
