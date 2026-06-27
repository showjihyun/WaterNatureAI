"""단위 테스트: normalize.py — parse_kst / parse_won / sha256_norm / derive_status.

정본: collector-narajangter.md §12 / coding-testing.md §3.
외부 IO 없음. DB 불필요.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.collectors.normalize import (
    KST,
    derive_status,
    parse_kst,
    parse_won,
    sha256_norm,
    split_reqst_period,
)


# ── parse_kst ────────────────────────────────────────────────────────────

class TestParseKst:
    def test_format_datetime_with_seconds(self):
        """"2026-06-16 18:00:00" 포맷."""
        result = parse_kst("2026-06-16 18:00:00")
        assert result is not None
        assert result.tzinfo == KST
        assert result.year == 2026
        assert result.month == 6
        assert result.day == 16
        assert result.hour == 18
        assert result.minute == 0

    def test_format_datetime_no_seconds(self):
        """"2026-06-16 18:00" 포맷."""
        result = parse_kst("2026-06-16 18:00")
        assert result is not None
        assert result.tzinfo == KST
        assert result.hour == 18

    def test_format_yyyymmddhhmm(self):
        """"202606161800" 포맷 (나라장터 inqryBgnDt 포맷)."""
        result = parse_kst("202606161800")
        assert result is not None
        assert result.tzinfo == KST
        assert result.year == 2026
        assert result.month == 6
        assert result.day == 16
        assert result.hour == 18

    def test_format_date_only_hyphen(self):
        """"2026-06-16" 날짜만 포맷."""
        result = parse_kst("2026-06-16")
        assert result is not None
        assert result.tzinfo == KST
        assert result.hour == 0
        assert result.minute == 0

    def test_format_date_only_compact(self):
        """"20260616" 날짜만 compact 포맷."""
        result = parse_kst("20260616")
        assert result is not None
        assert result.tzinfo == KST
        assert result.day == 16

    def test_none_input_returns_none(self):
        assert parse_kst(None) is None

    def test_empty_string_returns_none(self):
        assert parse_kst("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_kst("   ") is None

    def test_invalid_format_returns_none(self):
        """파싱 실패 시 None 반환 (레코드 버리지 않음)."""
        result = parse_kst("상시모집")
        assert result is None

    @pytest.mark.parametrize(
        "sentinel",
        ["상시", "예산소진시", "예산소진시까지", "별도공고", "추후공고", "별도", "추후"],
    )
    def test_freetext_sentinels_return_none(self, sentinel):
        """비정형 자유텍스트 → None (크래시 없이 레코드 보존).

        검증 완료: 나라장터(15129394) bidNtceDt/bidClseDt는 자유텍스트를 담지 않음
        (전자입찰 엔진상 고정 timestamp). 방어적으로 None 처리만 보장.
        그랜트성('상시' 등)은 기업마당/K-Startup 파서 담당.
        """
        assert parse_kst(sentinel) is None

    def test_tz_aware_kst(self):
        """결과가 KST(+09:00) tz-aware인지 확인."""
        result = parse_kst("2026-06-16 18:00:00")
        assert result is not None
        # KST = UTC+9
        assert result.utcoffset().total_seconds() == 9 * 3600

    def test_leading_whitespace_stripped(self):
        """앞뒤 공백 있어도 파싱."""
        result = parse_kst("  2026-06-16 18:00:00  ")
        assert result is not None
        assert result.year == 2026


# ── parse_won ────────────────────────────────────────────────────────────

class TestParseWon:
    def test_comma_separated(self):
        """"350,000,000" → 350000000."""
        assert parse_won("350,000,000") == 350000000

    def test_with_won_char(self):
        """"350,000,000원" → 350000000."""
        assert parse_won("350,000,000원") == 350000000

    def test_plain_digits(self):
        """"350000000" → 350000000."""
        assert parse_won("350000000") == 350000000

    def test_none_returns_none(self):
        assert parse_won(None) is None

    def test_empty_string_returns_none(self):
        assert parse_won("") is None

    def test_whitespace_only_returns_none(self):
        assert parse_won("   ") is None

    def test_no_digits_returns_none(self):
        """숫자 없는 문자열."""
        assert parse_won("원원원") is None

    def test_small_amount(self):
        assert parse_won("5,000,000") == 5000000

    def test_zero(self):
        assert parse_won("0") == 0

    # ── 한글 단위(억/만) 처리 (검증 후 활성화) ──────────────────────────
    def test_eok_unit(self):
        assert parse_won("15억") == 1_500_000_000

    def test_man_unit(self):
        assert parse_won("3,000만원") == 30_000_000

    def test_man_unit_no_won_suffix(self):
        assert parse_won("5,000만") == 50_000_000

    def test_eok_and_man_combined(self):
        """"3억 5,000만원" → 3*1e8 + 5000*1e4 = 350,000,000."""
        assert parse_won("3억 5,000만원") == 350_000_000

    def test_eok_only_with_spaces(self):
        assert parse_won("10억 원") == 1_000_000_000

    def test_unit_present_but_no_number_returns_none(self):
        """단위 문자만 있고 숫자 없음 → None."""
        assert parse_won("억") is None


# ── sha256_norm ──────────────────────────────────────────────────────────

class TestSha256Norm:
    def test_basic(self):
        """기본 동작: 동일 입력 → 동일 해시."""
        h1 = sha256_norm("사무용 PC", "서울시", None, 350000000, "설명")
        h2 = sha256_norm("사무용 PC", "서울시", None, 350000000, "설명")
        assert h1 == h2

    def test_length_64(self):
        """SHA-256 hex 길이 = 64."""
        h = sha256_norm("title", "agency")
        assert len(h) == 64

    def test_case_insensitive(self):
        """대소문자 정규화: 같은 해시."""
        h1 = sha256_norm("PC 구매", "서울시")
        h2 = sha256_norm("PC 구매", "서울시")
        assert h1 == h2

    def test_whitespace_normalization(self):
        """연속 공백 → 단일 스페이스."""
        h1 = sha256_norm("PC  구매", "서울시")
        h2 = sha256_norm("PC 구매", "서울시")
        assert h1 == h2

    def test_leading_trailing_whitespace(self):
        """앞뒤 공백 무시."""
        h1 = sha256_norm("  PC 구매  ", " 서울시 ")
        h2 = sha256_norm("PC 구매", "서울시")
        assert h1 == h2

    def test_none_treated_as_empty(self):
        """None은 빈 문자열로."""
        h1 = sha256_norm("title", None)
        h2 = sha256_norm("title", "")
        assert h1 == h2

    def test_field_change_produces_different_hash(self):
        """필드 값 변경 시 다른 해시."""
        h1 = sha256_norm("공고 A", "서울시")
        h2 = sha256_norm("공고 B", "서울시")
        assert h1 != h2

    def test_agency_change_produces_different_hash(self):
        """기관명 변경 시 다른 해시."""
        h1 = sha256_norm("공고 A", "서울시")
        h2 = sha256_norm("공고 A", "부산시")
        assert h1 != h2

    def test_order_matters(self):
        """필드 순서가 다르면 다른 해시."""
        h1 = sha256_norm("A", "B")
        h2 = sha256_norm("B", "A")
        assert h1 != h2

    def test_all_none(self):
        """모두 None이면 빈 문자열 결합."""
        h = sha256_norm(None, None, None)
        assert len(h) == 64

    def test_deadline_as_datetime_in_hash(self):
        """datetime 객체를 str(dt)로 변환 후 정규화."""
        dt = datetime(2026, 7, 10, 18, 0, 0, tzinfo=KST)
        h1 = sha256_norm("title", "agency", dt, 350000000, "desc")
        h2 = sha256_norm("title", "agency", dt, 350000000, "desc")
        assert h1 == h2

    def test_budget_amount_change_changes_hash(self):
        """예산액 변경 시 hash 변경 (content_hash 입력 필드 중 하나)."""
        h1 = sha256_norm("title", "agency", None, 350000000, "desc")
        h2 = sha256_norm("title", "agency", None, 360000000, "desc")
        assert h1 != h2


# ── derive_status ────────────────────────────────────────────────────────

class TestDeriveStatus:
    def test_open_future_deadline(self):
        """미래 마감일 → open."""
        future = datetime(2099, 12, 31, 18, 0, 0, tzinfo=timezone.utc)
        assert derive_status(future) == "open"

    def test_closed_past_deadline(self):
        """과거 마감일 → closed."""
        past = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert derive_status(past) == "closed"

    def test_unknown_none_deadline(self):
        """deadline None → unknown."""
        assert derive_status(None) == "unknown"

    def test_kst_deadline_open(self):
        """KST tz-aware 미래 deadline → open."""
        future_kst = datetime(2099, 12, 31, 18, 0, 0, tzinfo=KST)
        assert derive_status(future_kst) == "open"

    def test_kst_deadline_closed(self):
        """KST tz-aware 과거 deadline → closed."""
        past_kst = datetime(2020, 1, 1, 0, 0, 0, tzinfo=KST)
        assert derive_status(past_kst) == "closed"


# ── split_reqst_period (기업마당 reqstBeginEndDe) ─────────────────────────

class TestSplitReqstPeriod:
    def test_range_compact(self):
        """"YYYYMMDD ~ YYYYMMDD"."""
        start, end = split_reqst_period("20260601 ~ 20260630")
        assert start is not None and end is not None
        assert start.year == 2026 and start.month == 6 and start.day == 1
        assert end.day == 30
        assert start.tzinfo == KST and end.tzinfo == KST

    def test_range_dotted(self):
        """"YYYY.MM.DD~YYYY.MM.DD" (공백 없음, 점 구분)."""
        start, end = split_reqst_period("2026.06.01~2026.06.30")
        assert start is not None and end is not None
        assert start.month == 6 and end.day == 30

    def test_range_hyphen_dates_tilde_sep(self):
        """"YYYY-MM-DD ~ YYYY-MM-DD" (하이픈 날짜 + ~ 구분자)."""
        start, end = split_reqst_period("2026-06-01 ~ 2026-06-30")
        assert start is not None and end is not None
        assert start.day == 1 and end.day == 30

    def test_range_fullwidth_tilde(self):
        """전각 물결(～) 구분자."""
        start, end = split_reqst_period("20260601～20260630")
        assert start is not None and end is not None
        assert end.day == 30

    def test_single_date_is_deadline(self):
        """단일 날짜 → (None, 마감)."""
        start, end = split_reqst_period("20260630")
        assert start is None
        assert end is not None and end.day == 30

    def test_rolling_sangsi(self):
        """'상시' → (None, None)."""
        assert split_reqst_period("상시") == (None, None)

    def test_rolling_budget_exhausted(self):
        """'예산소진시까지' → (None, None)."""
        assert split_reqst_period("예산소진시까지") == (None, None)

    def test_rolling_with_dates_ignored(self):
        """'상시'가 포함되면 날짜가 있어도 비정형 처리."""
        assert split_reqst_period("2026.01.01 ~ 예산소진시") == (None, None)

    def test_none(self):
        assert split_reqst_period(None) == (None, None)

    def test_empty(self):
        assert split_reqst_period("") == (None, None)

    def test_whitespace(self):
        assert split_reqst_period("   ") == (None, None)

    def test_unparseable_range_returns_none_pair(self):
        """파싱 불가 토큰 → (None, None) (크래시 없음)."""
        start, end = split_reqst_period("미정 ~ 추후공지")
        # '추후'는 비정형 키워드 → (None, None)
        assert (start, end) == (None, None)

    def test_live_standard_format(self):
        """기업마당 라이브 표준 포맷 'YYYY-MM-DD ~ YYYY-MM-DD' (90%)."""
        start, end = split_reqst_period("2026-06-15 ~ 2026-06-29")
        assert start is not None and start.day == 15
        assert end is not None and end.day == 29

    @pytest.mark.parametrize(
        "value",
        [
            "예산 소진시까지", "상시 접수", "모집 완료시", "선착순 접수",
            "세부사업별 상이", "수시 모집", "차수별 상이", "수시 접수",
        ],
    )
    def test_live_nonstandard_values(self, value):
        """기업마당 라이브 실측 비정형 값(10%) → 모두 (None, None)."""
        assert split_reqst_period(value) == (None, None)
