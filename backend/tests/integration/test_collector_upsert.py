"""통합 테스트: NarajangterCollector.run() — UPSERT / 변경감지 / 재임베딩.

공용 픽스처(engine=alembic upgrade head, db_session, session_factory, embedding stub)는
tests/integration/conftest.py 참조. TEST_DATABASE_URL 없으면 skip.
seed(sources 5종)는 마이그레이션이 담당 → 여기서 sources 수동 삽입 안 함.

실행 방법:
    TEST_DATABASE_URL="postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar_test" \
        pytest tests/integration/test_collector_upsert.py -v
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.opportunity import (
    Opportunity,
    OpportunityChange,
    SourceIngestionState,
)
from app.services.collectors.base import _Window
from app.services.collectors.narajangter import NarajangterCollector

# ── pytest.skip 조건 (TEST_DATABASE_URL 없으면 모듈 전체 skip) ─────────────

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", ""),
    reason="TEST_DATABASE_URL not set — integration tests skipped",
)


# ── 가짜 Client ───────────────────────────────────────────────────────────

class _FixedPageClient:
    """고정된 페이지 목록을 반환하는 가짜 클라이언트."""

    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages
        self._call_count = 0

    def get(self, operation: str, params: dict) -> dict:
        idx = self._call_count
        self._call_count += 1
        if idx < len(self._pages):
            return {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
                        "items": self._pages[idx],
                        "totalCount": sum(len(p) for p in self._pages),
                        "numOfRows": 1000,
                        "pageNo": idx + 1,
                    },
                }
            }
        # 마지막 이후 → 빈 페이지
        return {
            "response": {
                "header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"},
                "body": {"items": "", "totalCount": 0, "numOfRows": 1000, "pageNo": idx + 1},
            }
        }

    @staticmethod
    def items(payload: dict) -> list[dict]:
        from app.services.collectors.client import DataGoKrClient  # noqa: PLC0415
        return DataGoKrClient.items(payload)

    @staticmethod
    def total_count(payload: dict) -> int | None:
        from app.services.collectors.client import DataGoKrClient  # noqa: PLC0415
        return DataGoKrClient.total_count(payload)


def _make_raw_item(
    bid_no: str = "20240600001",
    bid_ord: str = "000",
    title: str = "테스트 공고",
    agency: str = "테스트 기관",
    budget: str = "100,000,000",
    deadline: str = "2099-12-31 18:00:00",
) -> dict:
    return {
        "bidNtceNo": bid_no,
        "bidNtceOrd": bid_ord,
        "bidNtceNm": title,
        "ntceInsttNm": agency,
        "dminsttNm": None,
        "bidNtceDt": "2026-06-01 09:00:00",
        "bidClseDt": deadline,
        "presmptPrce": budget,
        "asignBdgtAmt": None,
        "bidNtceDtlUrl": f"https://www.g2b.go.kr/?no={bid_no}",
    }


def _build_collector(
    items_per_run: list[dict],
    session_factory: Callable,
) -> NarajangterCollector:
    """단일 페이지 가짜 클라이언트를 가진 collector 생성."""
    pages: list[list[dict]] = []
    for op, cat in [
        ("getBidPblancListInfoThng", "물품"),
        ("getBidPblancListInfoServc", "용역"),
        ("getBidPblancListInfoCnstwk", "공사"),
        ("getBidPblancListInfoFrgcpt", "외자"),
    ]:
        # 물품 op에만 items 할당 (나머지는 빈 페이지)
        if op == "getBidPblancListInfoThng":
            pages.append(items_per_run)
        else:
            pages.append([])  # NODATA처럼 동작

    client = _FixedPageClient(pages)
    collector = NarajangterCollector(client=client, session_factory=session_factory)
    return collector


# ── 테스트 케이스 ─────────────────────────────────────────────────────────

class TestCollectorUpsert:
    """UPSERT 왕복 테스트. source_ingestion_state 초기화 포함."""

    def _ensure_state(self, db: Session) -> None:
        """source_ingestion_state 행 없으면 초기 삽입 (FK 요구)."""
        if not db.get(SourceIngestionState, "narajangter"):
            db.add(SourceIngestionState(source="narajangter"))
            db.flush()

    # ── 케이스 1: 신규 INSERT ────────────────────────────────────────────

    def test_new_insert(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw = _make_raw_item(bid_no="T001")
        raw["_category"] = "물품"

        embed_mock = MagicMock()
        with patch(
            "app.services.embedding.tasks.embed_opportunity.delay", embed_mock
        ):
            collector = _build_collector([raw], session_factory)
            with patch.object(collector, "_window", return_value=_Window(
                begin=datetime.now(timezone.utc) - timedelta(days=1),
                end=datetime.now(timezone.utc),
            )):
                count = collector.run()

        assert count == 1
        opp = db_session.scalar(
            select(Opportunity).where(
                Opportunity.source == "narajangter",
                Opportunity.source_uid == "T001",
            )
        )
        assert opp is not None
        assert opp.title == "테스트 공고"
        assert opp.status == "open"
        assert opp.budget_amount == 100_000_000
        # 신규 → 변경으로 처리 → embed enqueue
        embed_mock.assert_called_once()

    # ── 케이스 2: 동일 재실행 (변경 없음) ───────────────────────────────

    def test_no_change_on_same_run(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw = _make_raw_item(bid_no="T002")
        raw["_category"] = "물품"

        embed_mock = MagicMock()
        with patch("app.services.embedding.tasks.embed_opportunity.delay", embed_mock):
            # 첫 번째 실행
            c1 = _build_collector([raw], session_factory)
            with patch.object(c1, "_window", return_value=_Window(
                begin=datetime.now(timezone.utc) - timedelta(days=1),
                end=datetime.now(timezone.utc),
            )):
                c1.run()

            first_call_count = embed_mock.call_count  # 1 (신규)

            # 두 번째 실행 (동일)
            c2 = _build_collector([dict(raw)], session_factory)
            with patch.object(c2, "_window", return_value=_Window(
                begin=datetime.now(timezone.utc) - timedelta(days=1),
                end=datetime.now(timezone.utc),
            )):
                c2.run()

        assert embed_mock.call_count == first_call_count  # 추가 enqueue 없음

        # OpportunityChange 건수 = 1 (신규 1건만)
        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "T002")
        )
        changes = db_session.execute(
            select(OpportunityChange).where(OpportunityChange.opportunity_id == opp.id)
        ).scalars().all()
        assert len(changes) == 1  # 신규 1건만

        # last_seen_at 갱신됐는지 확인
        assert opp.last_seen_at is not None

    # ── 케이스 3: 필드 변경 → UPDATE + OpportunityChange + 재임베딩 ──────

    def test_field_change_triggers_update(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw_v1 = _make_raw_item(bid_no="T003", budget="200,000,000")
        raw_v1["_category"] = "물품"

        embed_mock = MagicMock()
        with patch("app.services.embedding.tasks.embed_opportunity.delay", embed_mock):
            # 첫 번째 실행
            c1 = _build_collector([raw_v1], session_factory)
            with patch.object(c1, "_window", return_value=_Window(
                begin=datetime.now(timezone.utc) - timedelta(days=1),
                end=datetime.now(timezone.utc),
            )):
                c1.run()

            # 예산 변경 (content_hash 변경)
            raw_v2 = _make_raw_item(bid_no="T003", budget="250,000,000")
            raw_v2["_category"] = "물품"
            c2 = _build_collector([raw_v2], session_factory)
            with patch.object(c2, "_window", return_value=_Window(
                begin=datetime.now(timezone.utc) - timedelta(days=1),
                end=datetime.now(timezone.utc),
            )):
                c2.run()

        assert embed_mock.call_count == 2  # 신규 + 변경 → 2회 enqueue

        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "T003")
        )
        assert opp.budget_amount == 250_000_000  # 갱신됨

        changes = db_session.execute(
            select(OpportunityChange).where(OpportunityChange.opportunity_id == opp.id)
        ).scalars().all()
        assert len(changes) == 2  # 신규 + 변경 = 2건

    # ── 케이스 4: source_ingestion_state 갱신 ───────────────────────────

    def test_state_updated_on_success(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw = _make_raw_item(bid_no="T004")
        raw["_category"] = "물품"

        with patch("app.services.embedding.tasks.embed_opportunity.delay"):
            collector = _build_collector([raw], session_factory)
            with patch.object(collector, "_window", return_value=_Window(
                begin=datetime.now(timezone.utc) - timedelta(days=1),
                end=datetime.now(timezone.utc),
            )):
                collector.run()

        state = db_session.get(SourceIngestionState, "narajangter")
        assert state.last_status == "success"
        assert state.last_success_at is not None
        assert state.collected_count >= 1

    # ── 케이스 5: 정정공고 (bidNtceOrd 증가 + 내용 변경) ────────────────

    def test_amended_notice_creates_change(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw_v1 = _make_raw_item(bid_no="T005", bid_ord="000", budget="300,000,000")
        raw_v1["_category"] = "물품"

        embed_mock = MagicMock()
        with patch("app.services.embedding.tasks.embed_opportunity.delay", embed_mock):
            c1 = _build_collector([raw_v1], session_factory)
            with patch.object(c1, "_window", return_value=_Window(
                begin=datetime.now(timezone.utc) - timedelta(days=1),
                end=datetime.now(timezone.utc),
            )):
                c1.run()

            # 정정공고: 차수 증가 + 예산 변경
            raw_v2 = _make_raw_item(bid_no="T005", bid_ord="001", budget="350,000,000")
            raw_v2["_category"] = "물품"
            c2 = _build_collector([raw_v2], session_factory)
            with patch.object(c2, "_window", return_value=_Window(
                begin=datetime.now(timezone.utc) - timedelta(days=1),
                end=datetime.now(timezone.utc),
            )):
                c2.run()

        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "T005")
        )
        assert opp.source_ord == 1  # 최신 차수로 갱신

        changes = db_session.execute(
            select(OpportunityChange).where(OpportunityChange.opportunity_id == opp.id)
        ).scalars().all()
        assert len(changes) == 2  # 신규 + 정정

        # old_ord=0, new_ord=1 기록 확인
        latest_change = sorted(changes, key=lambda c: c.changed_at)[-1]
        assert latest_change.old_ord == 0
        assert latest_change.new_ord == 1

        assert embed_mock.call_count == 2  # 정정공고 → 재임베딩
