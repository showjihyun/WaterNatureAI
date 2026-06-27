"""단위 테스트: KStartupCollector.parse_item — DTO 필드 매핑 검증.

현실적인 K-Startup raw item fixture 사용 (설계문서 기준 추정 필드명).
DB/HTTP 없음.
⚠️ TODO(검증): 필드명은 실측 후 fixture/assertion 수정 필요.
정본: collector-kstartup-ntis.md §1.2
"""
from __future__ import annotations

import pytest

from app.services.collectors.kstartup import KStartupCollector
from app.services.collectors.normalize import sha256_norm


# ── 더미 클라이언트 ──────────────────────────────────────────────────────────

class _DummyClient:
    def get(self, *a, **kw):  # type: ignore[override]
        return {}

    @staticmethod
    def items(payload):
        return []

    @staticmethod
    def total_count(payload):
        return None


@pytest.fixture()
def collector() -> KStartupCollector:
    return KStartupCollector(client=_DummyClient())  # type: ignore[arg-type]


# ── K-Startup raw item fixtures ──────────────────────────────────────────────

@pytest.fixture()
def kstartup_item_open() -> dict:
    """현실적 K-Startup 공고 raw item (설계문서 기준 필드명, TODO(검증) 표기).

    ⚠️ 필드명은 data.go.kr 15125364 실측 전 추정값.
    """
    return {
        # TODO(검증): 공고 일련번호 키명 확인
        "pbancSn": "KS2026001234",
        # TODO(검증): 공고명 필드명 확인
        "biz_pbanc_nm": "2026년 예비창업패키지 지원사업 공고",
        # TODO(검증): 공고기관명 필드명 확인
        "pbanc_ntrp_nm": "창업진흥원",
        # TODO(검증): 지원사업분류 필드명 확인
        "supt_biz_clsfc": "예비창업",
        # TODO(검증): 접수시작일 필드명/포맷 확인
        "pbanc_rcpt_bgng_dt": "20260601",
        # TODO(검증): 접수종료일 필드명/포맷 확인
        "pbanc_rcpt_end_dt": "20991231",
        # TODO(검증): 지원지역 필드명 확인
        "supt_regin": "전국",
        # TODO(검증): 상세URL 필드명 확인
        "detl_pg_url": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=KS2026001234",
    }


@pytest.fixture()
def kstartup_item_no_deadline() -> dict:
    """마감일 없는 공고 (deadline=None → status=unknown)."""
    return {
        "pbancSn": "KS2026009999",
        "biz_pbanc_nm": "상시 모집 공고",
        "pbanc_ntrp_nm": "중소벤처기업부",
        "supt_biz_clsfc": "창업일반",
        "pbanc_rcpt_bgng_dt": "20260101",
        "pbanc_rcpt_end_dt": None,
        "supt_regin": None,
        "detl_pg_url": None,
    }


@pytest.fixture()
def kstartup_item_closed() -> dict:
    """마감된 공고 (deadline 과거)."""
    return {
        "pbancSn": "KS2023000001",
        "biz_pbanc_nm": "2023년 초기창업패키지 공고",
        "pbanc_ntrp_nm": "창업진흥원",
        "supt_biz_clsfc": "초기창업",
        "pbanc_rcpt_bgng_dt": "20230101",
        "pbanc_rcpt_end_dt": "20230131",
        "supt_regin": "수도권",
        "detl_pg_url": "https://www.k-startup.go.kr/web/contents/bizpbanc-ongoing.do?pbancSn=KS2023000001",
    }


# ── 기본 필드 파싱 ───────────────────────────────────────────────────────────

class TestKStartupParseBasic:
    def test_source_is_kstartup(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.source == "kstartup"

    def test_source_uid_extracted(self, collector, kstartup_item_open):
        """source_uid = 공고 일련번호 (pbancSn 후보). TODO(검증)."""
        dto = collector.parse_item(kstartup_item_open)
        assert dto.source_uid == "KS2026001234"

    def test_source_ord_is_none(self, collector, kstartup_item_open):
        """K-Startup은 차수 개념 없음 → source_ord=None."""
        dto = collector.parse_item(kstartup_item_open)
        assert dto.source_ord is None

    def test_title_stripped(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.title == "2026년 예비창업패키지 지원사업 공고"

    def test_agency_extracted(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.agency == "창업진흥원"

    def test_category_extracted(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.category == "예비창업"

    def test_region_extracted(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.region == "전국"

    def test_detail_url_extracted(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.detail_url is not None
        assert "k-startup.go.kr" in dto.detail_url

    def test_budget_is_none(self, collector, kstartup_item_open):
        """K-Startup 목록에 예산 없음 → None."""
        dto = collector.parse_item(kstartup_item_open)
        assert dto.budget_raw is None
        assert dto.budget_amount is None

    def test_application_start_at_parsed(self, collector, kstartup_item_open):
        """pbanc_rcpt_bgng_dt → application_start_at (p0-spec §3 정정)."""
        dto = collector.parse_item(kstartup_item_open)
        assert dto.application_start_at is not None
        assert dto.application_start_at.year == 2026
        assert dto.application_start_at.month == 6

    def test_deadline_parsed(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.deadline is not None
        assert dto.deadline.year == 2099

    def test_status_open(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.status == "open"

    def test_posted_at_none_when_no_reg_field(self, collector, kstartup_item_open):
        """등록일 필드 없으면 posted_at=None (정상). TODO(검증)."""
        dto = collector.parse_item(kstartup_item_open)
        # fixture에 reg_dt/creat_dt 없음 → None
        assert dto.posted_at is None

    def test_raw_json_preserved(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert dto.raw_json["pbancSn"] == "KS2026001234"


# ── content_hash ─────────────────────────────────────────────────────────────

class TestKStartupContentHash:
    def test_hash_64_chars(self, collector, kstartup_item_open):
        dto = collector.parse_item(kstartup_item_open)
        assert len(dto.content_hash) == 64

    def test_hash_deterministic(self, collector, kstartup_item_open):
        dto1 = collector.parse_item(kstartup_item_open)
        dto2 = collector.parse_item(dict(kstartup_item_open))
        assert dto1.content_hash == dto2.content_hash

    def test_hash_matches_sha256_norm(self, collector, kstartup_item_open):
        """content_hash = sha256_norm(title|agency|deadline|None|description)."""
        dto = collector.parse_item(kstartup_item_open)
        expected = sha256_norm(dto.title, dto.agency, dto.deadline, None, dto.description)
        assert dto.content_hash == expected

    def test_hash_changes_when_title_changes(self, collector, kstartup_item_open):
        dto1 = collector.parse_item(kstartup_item_open)
        modified = dict(kstartup_item_open)
        modified["biz_pbanc_nm"] = "변경된 공고명"
        dto2 = collector.parse_item(modified)
        assert dto1.content_hash != dto2.content_hash


# ── deadline/status 엣지 케이스 ─────────────────────────────────────────────

class TestKStartupDeadlineEdge:
    def test_no_deadline_status_unknown(self, collector, kstartup_item_no_deadline):
        dto = collector.parse_item(kstartup_item_no_deadline)
        assert dto.deadline is None
        assert dto.status == "unknown"

    def test_closed_status(self, collector, kstartup_item_closed):
        dto = collector.parse_item(kstartup_item_closed)
        assert dto.status == "closed"

    def test_no_region_is_none(self, collector, kstartup_item_no_deadline):
        dto = collector.parse_item(kstartup_item_no_deadline)
        assert dto.region is None

    def test_no_detail_url_is_none(self, collector, kstartup_item_no_deadline):
        dto = collector.parse_item(kstartup_item_no_deadline)
        assert dto.detail_url is None


# ── 방어 케이스 ─────────────────────────────────────────────────────────────

class TestKStartupDefensive:
    def test_empty_item_no_exception(self, collector):
        """모든 필드 없어도 예외 없음."""
        dto = collector.parse_item({})
        assert dto.source == "kstartup"
        assert dto.title == ""
        assert dto.source_uid == ""
        assert dto.agency is None
        assert dto.deadline is None
        assert dto.status == "unknown"

    def test_none_values_no_exception(self, collector):
        """None 값 전달에도 예외 없음."""
        raw = {
            "pbancSn": None,
            "biz_pbanc_nm": None,
            "pbanc_ntrp_nm": None,
            "pbanc_rcpt_end_dt": None,
        }
        dto = collector.parse_item(raw)
        assert dto.title == ""
        assert dto.source_uid == ""
