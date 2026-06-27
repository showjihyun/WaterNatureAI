"""통합 테스트: ScsbidCollector.run() — UPSERT / 변경감지 / 상태관리.

공용 픽스처(engine=alembic upgrade head, db_session, session_factory, embedding stub)는
tests/integration/conftest.py 참조. TEST_DATABASE_URL 없으면 skip.
sources 시드('narajangter_scsbid' 포함)는 마이그레이션이 담당 → 여기서 수동 삽입 안 함.
임베딩 enqueue가 호출되지 않음도 검증.

실행 방법:
    TEST_DATABASE_URL="postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar_test" \\
        pytest tests/integration/test_scsbid_upsert.py -v
"""
from __future__ import annotations

import os
from typing import Callable
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.opportunity import OpportunityAward, SourceIngestionState
from app.services.collectors.scsbid import ScsbidCollector

# ── pytest.skip 조건 (TEST_DATABASE_URL 없으면 모듈 전체 skip) ─────────────

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", ""),
    reason="TEST_DATABASE_URL not set — integration tests skipped",
)


# ── 가짜 Client ───────────────────────────────────────────────────────────

class _FixedPageClient:
    """고정된 페이지 목록을 반환하는 가짜 클라이언트 (ScsbidCollector용)."""

    def __init__(self, pages_per_op: list[list[dict]]) -> None:
        """pages_per_op: 4 ops 순서대로 [물품items, 용역items, 공사items, 외자items]."""
        self._pages_per_op = pages_per_op
        self._op_call_idx: dict[str, int] = {}

    def get(self, operation: str, params: dict) -> dict:
        idx = self._op_call_idx.get(operation, 0)
        self._op_call_idx[operation] = idx + 1

        op_pages = self._pages_per_op_map().get(operation, [[]])
        page_items = op_pages[idx] if idx < len(op_pages) else []

        if not page_items:
            return {
                "response": {
                    "header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"},
                    "body": {"items": "", "totalCount": 0, "numOfRows": 1000, "pageNo": idx + 1},
                }
            }

        all_items = [item for p in op_pages for item in p]
        return {
            "response": {
                "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                "body": {
                    "items": page_items,
                    "totalCount": len(all_items),
                    "numOfRows": 1000,
                    "pageNo": idx + 1,
                },
            }
        }

    def _pages_per_op_map(self) -> dict[str, list[list[dict]]]:
        ops = [
            "getScsbidListSttusThng",
            "getScsbidListSttusServc",
            "getScsbidListSttusCnstwk",
            "getScsbidListSttusFrgcpt",
        ]
        return {op: [self._pages_per_op[i]] for i, op in enumerate(ops)}

    @staticmethod
    def items(payload: dict) -> list[dict]:
        from app.services.collectors.client import DataGoKrClient  # noqa: PLC0415
        return DataGoKrClient.items(payload)

    @staticmethod
    def total_count(payload: dict) -> int | None:
        from app.services.collectors.client import DataGoKrClient  # noqa: PLC0415
        return DataGoKrClient.total_count(payload)


def _make_award_raw(
    bid_no: str = "R25BK00001111",
    bid_ord: str = "000",
    clsfc_no: str = "1",
    rbid_no: str = "000",
    winner_bizno: str = "1234567890",
    award_amount: str = "100000000",
    final_date: str = "2025-07-01",
) -> dict:
    return {
        "bidNtceNo": bid_no,
        "bidNtceOrd": bid_ord,
        "bidClsfcNo": clsfc_no,
        "rbidNo": rbid_no,
        "bidNtceNm": f"테스트 낙찰공고 {bid_no}",
        "prtcptCnum": "3",
        "bidwinnrNm": "테스트주식회사",
        "bidwinnrBizno": winner_bizno,
        "sucsfbidAmt": award_amount,
        "sucsfbidRate": "95.00",
        "rlOpengDt": "2025-07-01 10:00:00",
        "dminsttNm": "테스트 수요기관",
        "rgstDt": "2025-07-01 14:00:00",
        "fnlSucsfDate": final_date,
    }


def _build_collector(
    thng_items: list[dict],
    session_factory: Callable,
) -> ScsbidCollector:
    """물품에만 items 할당, 나머지 ops는 빈 페이지."""
    client = _FixedPageClient([thng_items, [], [], []])
    return ScsbidCollector(client=client, session_factory=session_factory)


# ── 테스트 케이스 ─────────────────────────────────────────────────────────

class TestScsbidUpsert:
    """ScsbidCollector UPSERT 왕복 테스트."""

    def _ensure_state(self, db: Session) -> None:
        if not db.get(SourceIngestionState, "narajangter_scsbid"):
            db.add(SourceIngestionState(source="narajangter_scsbid"))
            db.flush()

    # ── 케이스 1: 신규 INSERT ────────────────────────────────────────────

    def test_new_insert(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw = _make_award_raw(bid_no="A001")

        embed_mock = MagicMock()
        with patch("app.services.embedding.tasks.embed_opportunity.delay", embed_mock):
            collector = _build_collector([raw], session_factory)
            count = collector.run()

        assert count == 1

        award = db_session.scalar(
            select(OpportunityAward).where(
                OpportunityAward.source == "narajangter_scsbid",
                OpportunityAward.bid_ntce_no == "A001",
            )
        )
        assert award is not None
        assert award.winner_bizno == "1234567890"
        assert award.award_amount == 100_000_000
        assert award.category == "물품"

        # 임베딩 enqueue 없음
        embed_mock.assert_not_called()

    # ── 케이스 2: 동일 재실행 → 무변경 (last_seen_at만 갱신) ────────────

    def test_no_change_on_same_run(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw = _make_award_raw(bid_no="A002")

        embed_mock = MagicMock()
        with patch("app.services.embedding.tasks.embed_opportunity.delay", embed_mock):
            c1 = _build_collector([raw], session_factory)
            c1.run()

            c2 = _build_collector([dict(raw)], session_factory)
            c2.run()

        award_after = db_session.scalar(
            select(OpportunityAward).where(OpportunityAward.bid_ntce_no == "A002")
        )
        # 내용 불변 확인 (content_hash 동일)
        assert award_after.award_amount == 100_000_000
        # 임베딩 enqueue 없음 (두 번 실행 모두)
        embed_mock.assert_not_called()

    # ── 케이스 3: 낙찰금액 변경 → UPDATE ───────────────────────────────

    def test_amount_change_triggers_update(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw_v1 = _make_award_raw(bid_no="A003", award_amount="80000000")

        embed_mock = MagicMock()
        with patch("app.services.embedding.tasks.embed_opportunity.delay", embed_mock):
            c1 = _build_collector([raw_v1], session_factory)
            c1.run()

            raw_v2 = _make_award_raw(bid_no="A003", award_amount="85000000")
            c2 = _build_collector([raw_v2], session_factory)
            c2.run()

        award = db_session.scalar(
            select(OpportunityAward).where(OpportunityAward.bid_ntce_no == "A003")
        )
        assert award.award_amount == 85_000_000  # 갱신됨

        # 임베딩 enqueue 없음 (awards는 embed 안 함)
        embed_mock.assert_not_called()

    # ── 케이스 4: state.last_success_at 갱신 ───────────────────────────

    def test_state_updated_on_success(self, db_session: Session, session_factory):
        self._ensure_state(db_session)
        raw = _make_award_raw(bid_no="A004")

        with patch("app.services.embedding.tasks.embed_opportunity.delay"):
            collector = _build_collector([raw], session_factory)
            collector.run()

        state = db_session.get(SourceIngestionState, "narajangter_scsbid")
        assert state.last_status == "success"
        assert state.last_success_at is not None
        assert state.collected_count >= 1

    # ── 케이스 5: 임베딩 enqueue가 호출되지 않음 (명시 검증) ─────────────

    def test_embed_never_called(self, db_session: Session, session_factory):
        """awards 수집기는 어떤 경우에도 embed_opportunity.delay를 호출하지 않는다."""
        self._ensure_state(db_session)
        raw_v1 = _make_award_raw(bid_no="A005", award_amount="50000000")
        raw_v2 = _make_award_raw(bid_no="A005", award_amount="60000000")

        embed_mock = MagicMock()
        with patch("app.services.embedding.tasks.embed_opportunity.delay", embed_mock):
            # 신규 INSERT
            c1 = _build_collector([raw_v1], session_factory)
            c1.run()
            # 금액 변경 → UPDATE
            c2 = _build_collector([raw_v2], session_factory)
            c2.run()
            # 동일 재실행 → last_seen_at만
            c3 = _build_collector([dict(raw_v2)], session_factory)
            c3.run()

        embed_mock.assert_not_called()
