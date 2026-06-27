# -*- coding: utf-8 -*-
"""수집기 라이브 새로고침 — narajangter 상태 복구(누락 시) 후 3개 수집기 run().

narajangter는 state 행이 없어 그대로 run()하면 90일 백필 → 최신 수집일로 last_success를
복구해 증분 윈도우(~며칠)로 제한. kstartup·ntis는 기존 state로 증분.
"""
from __future__ import annotations

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from datetime import datetime, timezone

from sqlalchemy import func, select

from app.db.base import SessionLocal
from app.db.models.opportunity import Opportunity, SourceIngestionState
from app.services.collectors.registry import COLLECTORS


def repair_narajangter_state() -> None:
    db = SessionLocal()
    try:
        st = db.get(SourceIngestionState, "narajangter")
        if st is not None and st.last_success_at is not None:
            print(f"narajangter state OK (last_success={st.last_success_at})")
            return
        latest = db.scalar(
            select(func.max(Opportunity.created_at)).where(Opportunity.source == "narajangter")
        )
        if st is None:
            st = SourceIngestionState(source="narajangter")
            db.add(st)
        st.last_success_at = latest or datetime.now(timezone.utc)
        st.last_status = "success"
        db.commit()
        print(f"narajangter state 복구: last_success={st.last_success_at} (증분 윈도우로 제한)")
    finally:
        db.close()


def main() -> None:
    repair_narajangter_state()
    print("--- run() ---")
    for src, cls in COLLECTORS.items():
        t0 = datetime.now(timezone.utc)
        try:
            n = cls().run()
            secs = (datetime.now(timezone.utc) - t0).total_seconds()
            print(f"{src}: collected {n} ({secs:.0f}s)")
        except Exception as exc:  # noqa: BLE001
            print(f"{src}: FAILED {type(exc).__name__}: {str(exc)[:180]}")


if __name__ == "__main__":
    main()
