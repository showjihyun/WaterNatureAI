"""통합 테스트: NtisCollector.run() — UPSERT / 변경감지 / embed enqueue.

공용 픽스처(engine=alembic upgrade head, db_session, session_factory, stub)는
tests/integration/conftest.py 참조. TEST_DATABASE_URL 없으면 skip.
sources 시드('ntis' 포함)는 마이그레이션이 담당.

핵심 검증: requires_detail=False → 변경분은 embed_opportunity.delay 호출.
마감 미제공(항상 None) → 상태는 게시일 신선도 기반(최근=open).

실행 방법:
    TEST_DATABASE_URL="postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar_test" \
        pytest tests/integration/test_ntis_upsert.py -v
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Callable
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.opportunity import Opportunity, OpportunityChange, SourceIngestionState
from app.services.collectors.base import _Window
from app.services.collectors.client import DataGoKrClient
from app.services.collectors.ntis import NtisCollector

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", ""),
    reason="TEST_DATABASE_URL not set — integration tests skipped",
)


# ── 가짜 Client ──────────────────────────────────────────────────────────────

class _FixedPageClient:
    """고정된 pages를 순서대로 반환하는 가짜 DataGoKrClient."""

    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages
        self._call_count = 0

    def get(self, operation: str, params: dict) -> dict:  # noqa: ARG002
        idx = self._call_count
        self._call_count += 1
        if idx < len(self._pages):
            return {
                "response": {
                    "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
                    "body": {
                        "items": self._pages[idx],
                        "totalCount": sum(len(p) for p in self._pages),
                        "numOfRows": 100,
                        "pageNo": idx + 1,
                    },
                }
            }
        return {
            "response": {
                "header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"},
                "body": {"items": "", "totalCount": 0, "numOfRows": 100, "pageNo": idx + 1},
            }
        }

    @staticmethod
    def items(payload: dict) -> list[dict]:
        return DataGoKrClient.items(payload)

    @staticmethod
    def total_count(payload: dict) -> int | None:
        return DataGoKrClient.total_count(payload)


def _make_item(
    sn: str = "3176928",
    title: str = "테스트 NTIS 공고",
    dept: str = "기초연구진흥과",
) -> dict:
    """테스트용 NTIS raw item (공식 명세 필드명). sn = viewUrl의 nttSeqNo(=source_uid)."""
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return {
        "subject": title,
        "viewUrl": f"https://www.msit.go.kr/bbs/view.do?sCode=user&nttSeqNo={sn}",
        "deptName": dept,
        "managerName": "홍길동",
        "managerTel": "044-202-0000",
        "pressDt": now_str,
    }


def _build_collector(items: list[dict], session_factory: Callable) -> NtisCollector:
    client = _FixedPageClient([items, []])
    return NtisCollector(client=client, session_factory=session_factory)  # type: ignore[arg-type]


def _recent_window() -> _Window:
    now = datetime.now(timezone.utc)
    return _Window(begin=now - timedelta(days=1), end=now)


# ── 테스트 ────────────────────────────────────────────────────────────────────

class TestNtisUpsert:
    def _ensure_state(self, db: Session) -> None:
        if not db.get(SourceIngestionState, "ntis"):
            db.add(SourceIngestionState(source="ntis"))
            db.flush()

    def test_new_insert_calls_embed_not_enrich(self, db_session, session_factory):
        """신규 → embed_opportunity.delay 호출 (requires_detail=False)."""
        self._ensure_state(db_session)
        item = _make_item(sn="NTIS_U001")

        with patch("app.services.embedding.tasks.embed_opportunity.delay") as embed, \
             patch("app.services.collectors.tasks.enrich_detail.delay") as enrich:
            collector = _build_collector([item], session_factory)
            with patch.object(collector, "_window", return_value=_recent_window()):
                count = collector.run()

        assert count == 1
        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "NTIS_U001")
        )
        assert opp is not None
        assert opp.source == "ntis"
        assert opp.title == "테스트 NTIS 공고"
        assert opp.agency == "과학기술정보통신부 기초연구진흥과"
        assert opp.budget_amount is None
        # requires_detail=False: embed 호출, enrich 미호출
        embed.assert_called_once()
        enrich.assert_not_called()

    def test_no_change_on_same_run(self, db_session, session_factory):
        """동일 내용 재실행 → embed 추가 호출 없음."""
        self._ensure_state(db_session)
        item = _make_item(sn="NTIS_U002")

        with patch("app.services.embedding.tasks.embed_opportunity.delay") as embed, \
             patch("app.services.collectors.tasks.enrich_detail.delay"):
            c1 = _build_collector([item], session_factory)
            with patch.object(c1, "_window", return_value=_recent_window()):
                c1.run()
            first_count = embed.call_count

            c2 = _build_collector([dict(item)], session_factory)
            with patch.object(c2, "_window", return_value=_recent_window()):
                c2.run()

        assert embed.call_count == first_count

        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "NTIS_U002")
        )
        changes = db_session.execute(
            select(OpportunityChange).where(OpportunityChange.opportunity_id == opp.id)
        ).scalars().all()
        assert len(changes) == 1  # 신규 1건만

    def test_field_change_triggers_update_and_embed(self, db_session, session_factory):
        """필드 변경 → UPDATE + OpportunityChange + embed 재호출."""
        self._ensure_state(db_session)
        v1 = _make_item(sn="NTIS_U003", title="원래 공고명")

        with patch("app.services.embedding.tasks.embed_opportunity.delay") as embed, \
             patch("app.services.collectors.tasks.enrich_detail.delay"):
            c1 = _build_collector([v1], session_factory)
            with patch.object(c1, "_window", return_value=_recent_window()):
                c1.run()

            v2 = _make_item(sn="NTIS_U003", title="변경된 공고명")
            c2 = _build_collector([v2], session_factory)
            with patch.object(c2, "_window", return_value=_recent_window()):
                c2.run()

        assert embed.call_count == 2

        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "NTIS_U003")
        )
        assert opp.title == "변경된 공고명"
        changes = db_session.execute(
            select(OpportunityChange).where(OpportunityChange.opportunity_id == opp.id)
        ).scalars().all()
        assert len(changes) == 2

    def test_state_updated_on_success(self, db_session, session_factory):
        """성공 후 source_ingestion_state 갱신."""
        self._ensure_state(db_session)
        item = _make_item(sn="NTIS_U004")

        with patch("app.services.embedding.tasks.embed_opportunity.delay"), \
             patch("app.services.collectors.tasks.enrich_detail.delay"):
            collector = _build_collector([item], session_factory)
            with patch.object(collector, "_window", return_value=_recent_window()):
                collector.run()

        state = db_session.get(SourceIngestionState, "ntis")
        assert state.last_status == "success"
        assert state.last_success_at is not None
        assert state.collected_count >= 1

    def test_deadline_none_status_open_when_recent(self, db_session, session_factory):
        """마감 미제공(항상 None) + 최근 게시 → status=open (매칭 노출 가능)."""
        self._ensure_state(db_session)
        item = _make_item(sn="9000005")  # pressDt=now → open

        with patch("app.services.embedding.tasks.embed_opportunity.delay"), \
             patch("app.services.collectors.tasks.enrich_detail.delay"):
            collector = _build_collector([item], session_factory)
            with patch.object(collector, "_window", return_value=_recent_window()):
                collector.run()

        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "9000005")
        )
        assert opp is not None
        assert opp.deadline is None
        assert opp.status == "open"
