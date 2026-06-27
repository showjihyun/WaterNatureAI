"""통합 테스트: BizinfoCollector.run() — UPSERT / 변경감지 / enrich enqueue.

공용 픽스처(engine=alembic upgrade head, db_session, session_factory, stub)는
tests/integration/conftest.py 참조. TEST_DATABASE_URL 없으면 skip.
sources 시드('bizinfo' 포함)는 마이그레이션이 담당.

핵심 검증: requires_detail=True → 변경분은 embed가 아니라 enrich_detail.delay 호출
(list 단계 임베딩 보류). cutoff·멱등도 검증.

실행 방법:
    TEST_DATABASE_URL="postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar_test" \
        pytest tests/integration/test_bizinfo_upsert.py -v
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
from app.services.collectors.bizinfo import BizinfoCollector

pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL", ""),
    reason="TEST_DATABASE_URL not set — integration tests skipped",
)


# ── 가짜 Client ───────────────────────────────────────────────────────────

class _FixedPageClient:
    """첫 페이지에 items, 이후 빈 페이지를 반환하는 가짜 BizinfoClient."""

    def __init__(self, pages: list[list[dict]]) -> None:
        self._pages = pages
        self._idx = 0

    def fetch(self, page_index: int, page_unit: int) -> list[dict]:  # noqa: ARG002
        i = self._idx
        self._idx += 1
        return self._pages[i] if i < len(self._pages) else []


def _make_item(
    pblanc_id: str = "PBLN_000000000000001",
    title: str = "테스트 지원사업",
    period: str = "2026-06-15 ~ 2099-12-31",
    created: str | None = None,
) -> dict:
    if created is None:
        # 항상 윈도우 내(최근)로
        created = (datetime.now(timezone.utc) + timedelta(hours=9)).strftime("%Y-%m-%d %H:%M:%S")
    return {
        "pblancId": pblanc_id,
        "pblancNm": title,
        "jrsdInsttNm": "중소벤처기업부",
        "excInsttNm": "창업진흥원",
        "reqstBeginEndDe": period,
        "creatPnttm": created,
        "pldirSportRealmLclasCodeNm": "창업",
        "pblancUrl": f"https://www.bizinfo.go.kr/sii/siia/selectSIIA200Detail.do?pblancId={pblanc_id}",
    }


def _build_collector(items: list[dict], session_factory: Callable) -> BizinfoCollector:
    client = _FixedPageClient([items, []])
    return BizinfoCollector(client=client, session_factory=session_factory)


def _recent_window() -> _Window:
    now = datetime.now(timezone.utc)
    return _Window(begin=now - timedelta(days=1), end=now)


# ── 테스트 ────────────────────────────────────────────────────────────────

class TestBizinfoUpsert:
    def _ensure_state(self, db: Session) -> None:
        if not db.get(SourceIngestionState, "bizinfo"):
            db.add(SourceIngestionState(source="bizinfo"))
            db.flush()

    def test_new_insert_calls_enrich_not_embed(self, db_session, session_factory):
        """신규 → enrich_detail.delay 호출, embed_opportunity.delay 미호출."""
        self._ensure_state(db_session)
        item = _make_item(pblanc_id="PBLN_B001")

        with patch("app.services.collectors.tasks.enrich_detail.delay") as enrich, \
             patch("app.services.embedding.tasks.embed_opportunity.delay") as embed:
            collector = _build_collector([item], session_factory)
            with patch.object(collector, "_window", return_value=_recent_window()):
                count = collector.run()

        assert count == 1
        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "PBLN_B001")
        )
        assert opp is not None
        assert opp.source == "bizinfo"
        assert opp.budget_amount is None  # list 단계
        # requires_detail=True: enrich 호출, list 단계 embed 미호출
        enrich.assert_called_once()
        embed.assert_not_called()

    def test_no_change_on_same_run(self, db_session, session_factory):
        self._ensure_state(db_session)
        item = _make_item(pblanc_id="PBLN_B002")

        with patch("app.services.collectors.tasks.enrich_detail.delay") as enrich, \
             patch("app.services.embedding.tasks.embed_opportunity.delay"):
            c1 = _build_collector([item], session_factory)
            with patch.object(c1, "_window", return_value=_recent_window()):
                c1.run()
            first = enrich.call_count

            c2 = _build_collector([dict(item)], session_factory)
            with patch.object(c2, "_window", return_value=_recent_window()):
                c2.run()

        assert enrich.call_count == first  # 재실행 시 추가 enqueue 없음

        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "PBLN_B002")
        )
        changes = db_session.execute(
            select(OpportunityChange).where(OpportunityChange.opportunity_id == opp.id)
        ).scalars().all()
        assert len(changes) == 1  # 신규 1건만

    def test_field_change_triggers_update_and_enrich(self, db_session, session_factory):
        self._ensure_state(db_session)
        v1 = _make_item(pblanc_id="PBLN_B003", title="원래 사업명")

        with patch("app.services.collectors.tasks.enrich_detail.delay") as enrich, \
             patch("app.services.embedding.tasks.embed_opportunity.delay"):
            c1 = _build_collector([v1], session_factory)
            with patch.object(c1, "_window", return_value=_recent_window()):
                c1.run()

            v2 = _make_item(pblanc_id="PBLN_B003", title="변경된 사업명")
            c2 = _build_collector([v2], session_factory)
            with patch.object(c2, "_window", return_value=_recent_window()):
                c2.run()

        assert enrich.call_count == 2  # 신규 + 변경

        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "PBLN_B003")
        )
        assert opp.title == "변경된 사업명"
        changes = db_session.execute(
            select(OpportunityChange).where(OpportunityChange.opportunity_id == opp.id)
        ).scalars().all()
        assert len(changes) == 2

    def test_state_updated_on_success(self, db_session, session_factory):
        self._ensure_state(db_session)
        item = _make_item(pblanc_id="PBLN_B004")

        with patch("app.services.collectors.tasks.enrich_detail.delay"), \
             patch("app.services.embedding.tasks.embed_opportunity.delay"):
            collector = _build_collector([item], session_factory)
            with patch.object(collector, "_window", return_value=_recent_window()):
                collector.run()

        state = db_session.get(SourceIngestionState, "bizinfo")
        assert state.last_status == "success"
        assert state.last_success_at is not None
        assert state.collected_count >= 1

    def test_nonstandard_period_stored_unknown(self, db_session, session_factory):
        """비정형 신청기간 → deadline NULL, status unknown, 레코드 보존."""
        self._ensure_state(db_session)
        item = _make_item(pblanc_id="PBLN_B005", period="예산 소진시까지")

        with patch("app.services.collectors.tasks.enrich_detail.delay"), \
             patch("app.services.embedding.tasks.embed_opportunity.delay"):
            collector = _build_collector([item], session_factory)
            with patch.object(collector, "_window", return_value=_recent_window()):
                collector.run()

        opp = db_session.scalar(
            select(Opportunity).where(Opportunity.source_uid == "PBLN_B005")
        )
        assert opp is not None
        assert opp.deadline is None
        assert opp.status == "unknown"
