"""단위 테스트: NtisCollector.parse_item — DTO 필드 매핑 검증.

공식 명세(OpenApi활용가이드_과학기술정보통신부_사업공고_v1.0) 기반 fixture.
응답 필드: subject/viewUrl/deptName/pressDt/managerName/managerTel/files.
마감·예산·분류·지역·ID 미제공 → None / viewUrl의 nttSeqNo로 식별자 대체.
상태는 게시일 신선도 기반(open/closed). DB/HTTP 없음.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.services.collectors.ntis import _OPEN_WINDOW_DAYS, NtisCollector
from app.services.collectors.normalize import sha256_norm


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
def collector() -> NtisCollector:
    return NtisCollector(client=_DummyClient())  # type: ignore[arg-type]


def _recent_pressdt() -> str:
    return (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d")


@pytest.fixture()
def ntis_item() -> dict:
    """공식 명세 응답 예제 첫 item(게시일만 최근으로 조정)."""
    return {
        "subject": "『2021년도 공공연구성과 활용 촉진 R&D (중개연구플랫폼 구축)』사업 시행 공고",
        "viewUrl": "https://www.msit.go.kr/bbs/view.do?sCode=user&mId=129&mPid=128&bbsSeqNo=100&nttSeqNo=3176928",
        "deptName": "연구성과일자리정책과",
        "managerName": "최승호",
        "managerTel": "044-202-4723",
        "pressDt": _recent_pressdt(),
    }


class TestNtisParseBasic:
    def test_source_is_ntis(self, collector, ntis_item):
        assert collector.parse_item(ntis_item).source == "ntis"

    def test_source_uid_from_nttseqno(self, collector, ntis_item):
        """ID 필드 없음 → viewUrl의 nttSeqNo를 source_uid로."""
        assert collector.parse_item(ntis_item).source_uid == "3176928"

    def test_title_is_subject(self, collector, ntis_item):
        assert collector.parse_item(ntis_item).title.startswith("『2021년도 공공연구성과")

    def test_agency_is_ministry_plus_dept(self, collector, ntis_item):
        assert collector.parse_item(ntis_item).agency == "과학기술정보통신부 연구성과일자리정책과"

    def test_posted_at_parsed(self, collector, ntis_item):
        dto = collector.parse_item(ntis_item)
        assert dto.posted_at is not None

    def test_detail_url_is_viewurl(self, collector, ntis_item):
        assert collector.parse_item(ntis_item).detail_url.startswith("https://www.msit.go.kr")

    def test_deadline_budget_region_category_none(self, collector, ntis_item):
        """NTIS 목록은 마감·예산·지역·분류 미제공 → 모두 None."""
        dto = collector.parse_item(ntis_item)
        assert dto.deadline is None
        assert dto.budget_raw is None and dto.budget_amount is None
        assert dto.region is None
        assert dto.category is None
        assert dto.application_start_at is None
        assert dto.source_ord is None

    def test_description_includes_subject_and_ministry(self, collector, ntis_item):
        desc = collector.parse_item(ntis_item).description
        assert "과학기술정보통신부" in desc
        assert "공공연구성과" in desc

    def test_raw_json_preserved(self, collector, ntis_item):
        assert collector.parse_item(ntis_item).raw_json["managerName"] == "최승호"


class TestNtisStatusByRecency:
    def test_recent_is_open(self, collector, ntis_item):
        assert collector.parse_item(ntis_item).status == "open"

    def test_old_is_closed(self, collector, ntis_item):
        old = dict(ntis_item)
        old["pressDt"] = (
            datetime.now(timezone.utc) - timedelta(days=_OPEN_WINDOW_DAYS + 30)
        ).strftime("%Y-%m-%d")
        assert collector.parse_item(old).status == "closed"

    def test_doc_sample_2020_is_closed(self, collector, ntis_item):
        old = dict(ntis_item)
        old["pressDt"] = "2020-12-10"
        assert collector.parse_item(old).status == "closed"


class TestNtisContentHash:
    def test_hash_64_chars(self, collector, ntis_item):
        assert len(collector.parse_item(ntis_item).content_hash) == 64

    def test_hash_matches_sha256_norm(self, collector, ntis_item):
        dto = collector.parse_item(ntis_item)
        expected = sha256_norm(dto.title, dto.agency, None, None, dto.description)
        assert dto.content_hash == expected

    def test_hash_changes_when_subject_changes(self, collector, ntis_item):
        dto1 = collector.parse_item(ntis_item)
        modified = dict(ntis_item)
        modified["subject"] = "변경된 공고명"
        assert dto1.content_hash != collector.parse_item(modified).content_hash

    def test_hash_same_when_pressdt_changes_within_window(self, collector, ntis_item):
        """pressDt는 content_hash 입력 아님(상태에만 영향) — 같은 윈도우 내 변경 시 hash 동일."""
        dto1 = collector.parse_item(ntis_item)
        modified = dict(ntis_item)
        modified["pressDt"] = (
            datetime.now(timezone.utc) - timedelta(days=3)
        ).strftime("%Y-%m-%d")
        assert dto1.content_hash == collector.parse_item(modified).content_hash


class TestNtisDefensive:
    def test_empty_item_no_exception(self, collector):
        dto = collector.parse_item({})
        assert dto.source == "ntis"
        assert dto.title == ""
        assert dto.agency == "과학기술정보통신부"  # deptName 없음 → 부처만
        assert dto.deadline is None
        assert len(dto.content_hash) == 64

    def test_source_uid_fallback_hash_without_viewurl(self, collector):
        """viewUrl/nttSeqNo 없으면 subject+pressDt 해시(24자)."""
        raw = {"subject": "ID 없는 공고", "pressDt": "2026-06-01"}
        dto = collector.parse_item(raw)
        assert len(dto.source_uid) == 24
        # 동일 입력 → 동일 식별자(멱등)
        assert dto.source_uid == collector.parse_item(dict(raw)).source_uid

    def test_none_values_no_exception(self, collector):
        dto = collector.parse_item({"subject": None, "viewUrl": None, "pressDt": None})
        assert dto.title == ""
        assert dto.detail_url is None
