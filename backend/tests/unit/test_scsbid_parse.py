"""단위 테스트: ScsbidCollector parse_award_item — DTO 필드 매핑 검증.

README §4.3 기반 현실적 낙찰 raw item fixture 사용.
DB/HTTP 없음.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.services.collectors.normalize import KST, sha256_norm
from app.services.collectors.scsbid import SOURCE_CODE, AwardDTO, parse_award_item


# ── 픽스처 ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def scsbid_item_thng() -> dict:
    """물품 낙찰정보 raw item (README §4.3 검증 기준)."""
    return {
        "bidNtceNo": "R25BK00965123",
        "bidNtceOrd": "000",
        "bidClsfcNo": "1",
        "rbidNo": "000",
        "bidNtceNm": "2025년 보일러 구매 납품",
        "prtcptCnum": "2",
        "bidwinnrNm": "주식회사 동광보일러",
        "bidwinnrBizno": "1408121883",
        "bidwinnrCeoNm": "홍길동",
        "sucsfbidAmt": "83500000",
        "sucsfbidRate": "97.82",
        "rlOpengDt": "2025-07-23 11:00:00",
        "dminsttCd": "12345",
        "dminsttNm": "인천광역시 종합건설본부",
        "rgstDt": "2025-07-23 15:20:05",
        "fnlSucsfDate": "2025-07-23",
    }


@pytest.fixture()
def scsbid_item_no_winner() -> dict:
    """낙찰업체·금액 없는 방어 케이스 (일부 필드 NULL)."""
    return {
        "bidNtceNo": "R25BK00999999",
        "bidNtceOrd": "000",
        "bidClsfcNo": "2",
        "rbidNo": "000",
        "bidNtceNm": None,
        "prtcptCnum": None,
        "bidwinnrNm": None,
        "bidwinnrBizno": None,
        "sucsfbidAmt": None,
        "sucsfbidRate": None,
        "rlOpengDt": None,
        "dminsttNm": None,
        "rgstDt": None,
        "fnlSucsfDate": None,
    }


# ── 물품 낙찰 parse_award_item ─────────────────────────────────────────────

class TestParseAwardItemThng:
    def test_source_code(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.source == SOURCE_CODE
        assert dto.source == "narajangter_scsbid"

    def test_source_uid_composition(self, scsbid_item_thng):
        """source_uid = f"{bidNtceNo}-{bidNtceOrd}-{bidClsfcNo}-{rbidNo}"."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.source_uid == "R25BK00965123-000-1-000"

    def test_bid_ntce_no(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.bid_ntce_no == "R25BK00965123"

    def test_bid_ntce_ord_int(self, scsbid_item_thng):
        """'000' → 0 (int 변환)."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.bid_ntce_ord == 0

    def test_bid_clsfc_no(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.bid_clsfc_no == "1"

    def test_rbid_no(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.rbid_no == "000"

    def test_category(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.category == "물품"

    def test_title(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.title == "2025년 보일러 구매 납품"

    def test_winner_name(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.winner_name == "주식회사 동광보일러"

    def test_winner_bizno(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.winner_bizno == "1408121883"

    def test_award_amount(self, scsbid_item_thng):
        """sucsfbidAmt '83500000' → 83500000 (int)."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.award_amount == 83_500_000

    def test_award_rate(self, scsbid_item_thng):
        """sucsfbidRate '97.82' → Decimal('97.82')."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.award_rate == Decimal("97.82")

    def test_participant_count(self, scsbid_item_thng):
        """prtcptCnum '2' → 2 (int)."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.participant_count == 2

    def test_demand_agency(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.demand_agency == "인천광역시 종합건설본부"

    def test_real_opening_at_kst_aware(self, scsbid_item_thng):
        """rlOpengDt '2025-07-23 11:00:00' → KST aware datetime."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.real_opening_at is not None
        assert dto.real_opening_at.tzinfo == KST
        assert dto.real_opening_at.year == 2025
        assert dto.real_opening_at.hour == 11

    def test_final_award_date(self, scsbid_item_thng):
        """fnlSucsfDate '2025-07-23' → date(2025, 7, 23)."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.final_award_date == date(2025, 7, 23)

    def test_registered_at_kst_aware(self, scsbid_item_thng):
        """rgstDt '2025-07-23 15:20:05' → KST aware datetime."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.registered_at is not None
        assert dto.registered_at.tzinfo == KST
        assert dto.registered_at.hour == 15
        assert dto.registered_at.minute == 20

    def test_content_hash_64_chars(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert len(dto.content_hash) == 64

    def test_content_hash_deterministic(self, scsbid_item_thng):
        """같은 raw → 같은 content_hash."""
        dto1 = parse_award_item(scsbid_item_thng, "물품")
        dto2 = parse_award_item(scsbid_item_thng, "물품")
        assert dto1.content_hash == dto2.content_hash

    def test_content_hash_matches_sha256_norm(self, scsbid_item_thng):
        """content_hash = sha256_norm(bid_ntce_no, bid_ntce_ord, winner_bizno, award_amount, final_award_date)."""
        dto = parse_award_item(scsbid_item_thng, "물품")
        expected = sha256_norm(
            dto.bid_ntce_no, dto.bid_ntce_ord, dto.winner_bizno,
            dto.award_amount, dto.final_award_date,
        )
        assert dto.content_hash == expected

    def test_hash_changes_when_amount_changes(self, scsbid_item_thng):
        """낙찰금액 변경 시 content_hash 변경."""
        dto1 = parse_award_item(scsbid_item_thng, "물품")
        raw_v2 = dict(scsbid_item_thng)
        raw_v2["sucsfbidAmt"] = "85000000"
        dto2 = parse_award_item(raw_v2, "물품")
        assert dto1.content_hash != dto2.content_hash

    def test_raw_json_preserved(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert dto.raw_json["bidNtceNo"] == "R25BK00965123"

    def test_returns_award_dto(self, scsbid_item_thng):
        dto = parse_award_item(scsbid_item_thng, "물품")
        assert isinstance(dto, AwardDTO)


# ── 방어 케이스 (결측 필드) ─────────────────────────────────────────────────

class TestParseAwardItemDefensive:
    def test_no_exception_on_null_fields(self, scsbid_item_no_winner):
        """낙찰업체·금액 등 모든 선택 필드 None → 예외 없음."""
        dto = parse_award_item(scsbid_item_no_winner, "용역")
        assert dto.source == SOURCE_CODE
        assert dto.winner_name is None
        assert dto.winner_bizno is None
        assert dto.award_amount is None
        assert dto.award_rate is None
        assert dto.participant_count is None
        assert dto.demand_agency is None
        assert dto.real_opening_at is None
        assert dto.final_award_date is None
        assert dto.registered_at is None
        assert dto.title is None

    def test_no_exception_on_minimal_item(self):
        """최소 필드(bidNtceNo만 있는 dict) — 예외 없음."""
        raw = {"bidNtceNo": "MIN001"}
        dto = parse_award_item(raw, "공사")
        assert dto.bid_ntce_no == "MIN001"
        assert dto.bid_ntce_ord is None
        assert dto.award_amount is None
        assert dto.content_hash  # 64자

    def test_source_uid_with_none_fields(self):
        """bidNtceOrd/bidClsfcNo/rbidNo 없을 때 source_uid 빈 세그먼트 처리."""
        raw = {"bidNtceNo": "ABC001"}
        dto = parse_award_item(raw, "외자")
        # source_uid = "ABC001---" (None → '' 처리)
        assert dto.source_uid.startswith("ABC001-")

    def test_fnl_sucsf_date_invalid_format(self):
        """fnlSucsfDate 비정형 값 → None (경고, 예외 없음)."""
        raw = {
            "bidNtceNo": "ERR001",
            "bidNtceOrd": "000",
            "bidClsfcNo": "1",
            "rbidNo": "000",
            "fnlSucsfDate": "invalid-date",
        }
        dto = parse_award_item(raw, "물품")
        assert dto.final_award_date is None

    def test_award_rate_invalid_value(self):
        """sucsfbidRate 비정형 값 → None (경고, 예외 없음)."""
        raw = {
            "bidNtceNo": "ERR002",
            "bidNtceOrd": "000",
            "bidClsfcNo": "1",
            "rbidNo": "000",
            "sucsfbidRate": "N/A",
        }
        dto = parse_award_item(raw, "물품")
        assert dto.award_rate is None
