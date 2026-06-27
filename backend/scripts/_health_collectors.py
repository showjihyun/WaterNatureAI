# -*- coding: utf-8 -*-
"""수집기 헬스체크 — DB 신선도 + 라이브 API 도달성(읽기 전용, upsert 없음).

실행: $env:PYTHONPATH="...backend"; python scripts/_health_collectors.py
"""
from __future__ import annotations

import io
import sys
from datetime import datetime, timedelta, timezone

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from sqlalchemy import func, select

from app.db.base import SessionLocal
from app.db.models.opportunity import Opportunity, SourceIngestionState
from app.services.collectors.base import _Window
from app.services.collectors.registry import COLLECTORS

SOURCES = ["narajangter", "kstartup", "ntis"]


def _fmt(dt) -> str:
    if dt is None:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - dt
    days = delta.days
    ago = f"{days}일 전" if days >= 1 else f"{delta.seconds // 3600}시간 전"
    return f"{dt.date().isoformat()} ({ago})"


def db_report(db) -> None:
    now = datetime.now(timezone.utc)
    print("=" * 78)
    print("1) DB 신선도 (소스별)")
    print("=" * 78)
    for src in SOURCES:
        def c(*conds):
            return db.scalar(select(func.count()).select_from(Opportunity).where(Opportunity.source == src, *conds))

        total = c()
        open_ = c(Opportunity.status == "open")
        latest_posted = db.scalar(select(func.max(Opportunity.posted_at)).where(Opportunity.source == src))
        latest_created = db.scalar(select(func.max(Opportunity.created_at)).where(Opportunity.source == src))
        latest_seen = db.scalar(select(func.max(Opportunity.last_seen_at)).where(Opportunity.source == src))
        d7 = c(Opportunity.created_at >= now - timedelta(days=7))
        d14 = c(Opportunity.created_at >= now - timedelta(days=14))

        print(f"\n[{src}]")
        print(f"  공고: 총 {total} / open {open_} / 최근7일 신규 {d7} / 최근14일 {d14}")
        print(f"  최신 게시일(posted_at): {_fmt(latest_posted)}")
        print(f"  최신 수집(created_at) : {_fmt(latest_created)}")
        print(f"  최근 확인(last_seen)  : {_fmt(latest_seen)}")

        st = db.get(SourceIngestionState, src)
        if st is None:
            print("  수집상태: source_ingestion_state 행 없음 (아직 1회도 run() 안 됨?)")
        else:
            print(f"  수집상태: last_status={st.last_status} collected={st.collected_count}")
            print(f"           last_run={_fmt(st.last_run_at)} last_success={_fmt(st.last_success_at)}")
            if st.error_message:
                print(f"           error: {st.error_message[:160]}")


def live_probe() -> None:
    now = datetime.now(timezone.utc)
    window = _Window(begin=now - timedelta(days=14), end=now)
    print("\n" + "=" * 78)
    print("2) 라이브 API 도달성 (각 수집기 1페이지 프로브, 읽기 전용)")
    print("=" * 78)
    for src in SOURCES:
        cls = COLLECTORS.get(src)
        if cls is None:
            print(f"\n[{src}] 레지스트리 비활성 (COLLECTORS에 없음)")
            continue
        print(f"\n[{src}]")
        try:
            col = cls()
            pages = col.iter_pages(window)
            first = next(iter(pages), [])
            print(f"  ✓ 응답 OK — 1페이지 {len(first)}건")
            if first:
                dto = col.parse_item(first[0])
                title = (dto.title or "")[:48]
                print(f"    예시: '{title}' / posted={_fmt(dto.posted_at)} / status={dto.status}")
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ 실패: {type(exc).__name__}: {str(exc)[:200]}")


def main() -> None:
    db = SessionLocal()
    try:
        db_report(db)
    finally:
        db.close()
    live_probe()


if __name__ == "__main__":
    main()
