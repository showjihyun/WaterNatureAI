"""BaseCollector — 수집 파이프라인 공통 템플릿.

정본: docs/04-architecture/collector-base-bizinfo.md §1·§2, collector-narajangter.md.
소스별로 iter_pages/parse_item(/fetch_detail)만 구현하면 증분·UPSERT·변경감지·
재임베딩 enqueue·상태관리는 run()이 공통 처리.

테스트 용이성: session_factory를 생성자에서 주입 가능 (기본: app.db.base.SessionLocal).
subclass에서 self._session_factory = ... 로 override 가능.
"""
from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models.opportunity import (
    Opportunity,
    OpportunityChange,
    SourceIngestionState,
)
from app.services.collectors._redact import redact_secrets


@dataclass
class OpportunityDTO:
    source: str
    source_uid: str
    title: str
    content_hash: str
    raw_json: dict
    status: str = "unknown"
    source_ord: int | None = None
    detail_url: str | None = None
    agency: str | None = None
    category: str | None = None
    region: str | None = None
    description: str | None = None
    budget_raw: str | None = None
    budget_amount: int | None = None
    posted_at: datetime | None = None
    application_start_at: datetime | None = None
    deadline: datetime | None = None


@dataclass
class UpsertResult:
    id: uuid.UUID
    changed: bool
    old_hash: str | None = None
    old_ord: int | None = None


@dataclass
class _Window:
    begin: datetime
    end: datetime


def _default_session_factory() -> Callable[[], Session]:
    """실제 SessionLocal을 지연 import해서 반환 (순환 import 방지)."""
    from app.db.base import SessionLocal  # noqa: PLC0415
    return SessionLocal


class BaseCollector(ABC):
    source_code: str
    requires_detail: bool = False  # True면 list 단계 임베딩 보류 → 상세 후 임베딩

    # 기본 session_factory는 None → run()에서 _get_session_factory()를 통해 lazy 로딩
    # subclass 또는 테스트에서 self._session_factory 로 override 가능
    _session_factory: Callable | None = None

    def _get_session_factory(self) -> Callable:
        if self._session_factory is not None:
            return self._session_factory
        from app.db.base import SessionLocal  # noqa: PLC0415
        return SessionLocal

    # ── 소스별 구현 ──────────────────────────────────
    @abstractmethod
    def iter_pages(self, window: _Window) -> Iterator[list[dict]]: ...

    @abstractmethod
    def parse_item(self, raw: dict) -> OpportunityDTO: ...

    def fetch_detail(self, dto: OpportunityDTO) -> OpportunityDTO:  # 선택 override
        return dto

    # ── 공통 템플릿 ──────────────────────────────────
    def run(self) -> int:
        from app.services.embedding.tasks import embed_opportunity  # 지연 import(순환 방지)

        session_factory = self._get_session_factory()
        db: Session = session_factory()
        total = 0
        try:
            state = self._get_state(db)
            window = self._window(state)
            state.last_status = "running"
            state.last_run_at = datetime.now(timezone.utc)
            db.commit()

            for page_items in self.iter_pages(window):
                for raw in page_items:
                    dto = self.parse_item(raw)
                    res = self._upsert(db, dto)
                    if res.changed:
                        db.add(OpportunityChange(
                            opportunity_id=res.id,
                            old_hash=res.old_hash,
                            new_hash=dto.content_hash,
                            old_ord=res.old_ord,
                            new_ord=dto.source_ord,
                        ))
                        db.commit()
                        if self.requires_detail:
                            # 상세 보강 태스크에서 임베딩 enqueue (collector-base-bizinfo §3.4)
                            from app.services.collectors.tasks import enrich_detail  # noqa: PLC0415
                            enrich_detail.delay(self.source_code, str(res.id))
                        else:
                            embed_opportunity.delay(str(res.id))
                    total += 1

            state.last_status = "success"
            state.last_success_at = window.end
            state.collected_count = total
            state.error_message = None
            db.commit()
            return total

        except Exception as exc:  # noqa: BLE001 — 실패 격리, last_success 불변 → 재시도
            db.rollback()
            # 상태 갱신은 별도 트랜잭션으로
            try:
                state = self._get_state(db)
                state.last_status = "failed"
                state.error_message = redact_secrets(str(exc))
                db.commit()
            except Exception:  # noqa: BLE001
                db.rollback()
            raise
        finally:
            db.close()

    # ── 내부 ────────────────────────────────────────
    def _get_state(self, db: Session) -> SourceIngestionState:
        state = db.get(SourceIngestionState, self.source_code)
        if state is None:
            state = SourceIngestionState(source=self.source_code)
            db.add(state)
            db.commit()
        return state

    def _window(self, state: SourceIngestionState) -> _Window:
        end = datetime.now(timezone.utc)
        if state.last_success_at:
            begin = state.last_success_at - timedelta(days=settings.ingest_buffer_days)
        else:
            begin = end - timedelta(days=settings.ingest_backfill_days)  # 최초 백필
        return _Window(begin=begin, end=end)

    def _upsert(self, db: Session, dto: OpportunityDTO) -> UpsertResult:
        existing = db.scalar(
            select(Opportunity).where(
                Opportunity.source == dto.source,
                Opportunity.source_uid == dto.source_uid,
            )
        )
        now = datetime.now(timezone.utc)

        if existing is None:
            opp = Opportunity(
                source=dto.source,
                source_uid=dto.source_uid,
                source_ord=dto.source_ord,
                detail_url=dto.detail_url,
                title=dto.title,
                agency=dto.agency,
                category=dto.category,
                region=dto.region,
                description=dto.description,
                budget_raw=dto.budget_raw,
                budget_amount=dto.budget_amount,
                posted_at=dto.posted_at,
                application_start_at=dto.application_start_at,
                deadline=dto.deadline,
                status=dto.status,
                raw_json=dto.raw_json,
                content_hash=dto.content_hash,
                last_seen_at=now,
            )
            db.add(opp)
            db.commit()
            return UpsertResult(id=opp.id, changed=True)

        if existing.content_hash != dto.content_hash:
            old_hash, old_ord = existing.content_hash, existing.source_ord
            existing.source_ord = dto.source_ord
            existing.title = dto.title
            existing.agency = dto.agency
            existing.category = dto.category
            existing.region = dto.region
            existing.description = dto.description
            existing.budget_raw = dto.budget_raw
            existing.budget_amount = dto.budget_amount
            existing.posted_at = dto.posted_at
            existing.application_start_at = dto.application_start_at
            existing.deadline = dto.deadline
            existing.status = dto.status
            existing.raw_json = dto.raw_json
            existing.content_hash = dto.content_hash
            existing.last_seen_at = now
            db.commit()
            return UpsertResult(
                id=existing.id, changed=True, old_hash=old_hash, old_ord=old_ord
            )

        # 변경 없음 → last_seen_at 경량 갱신
        existing.last_seen_at = now
        db.commit()
        return UpsertResult(id=existing.id, changed=False)
