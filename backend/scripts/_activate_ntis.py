# -*- coding: utf-8 -*-
"""NTIS 수집 실행 + 적재 현황 출력."""
from __future__ import annotations

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import sqlalchemy as sa

from app.db.base import SessionLocal
from app.services.collectors.ntis import NtisCollector

n = NtisCollector().run()
print("ntis run() processed:", n)

db = SessionLocal()
total = db.scalar(sa.text("SELECT count(*) FROM opportunities WHERE source='ntis'"))
openc = db.scalar(sa.text("SELECT count(*) FROM opportunities WHERE source='ntis' AND status='open'"))
print(f"ntis opportunities: total={total} open={openc}")
rows = db.execute(sa.text(
    "SELECT title, agency, status, posted_at FROM opportunities WHERE source='ntis' "
    "ORDER BY posted_at DESC NULLS LAST LIMIT 5"
)).fetchall()
for r in rows:
    print("  -", (r.title or "")[:44], "|", (r.agency or "")[:24], "|", r.status, "|", r.posted_at)
db.close()
