# -*- coding: utf-8 -*-
"""K-Startup 수집 실행 + 적재 현황 출력."""
from __future__ import annotations

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import sqlalchemy as sa

from app.db.base import SessionLocal
from app.services.collectors.kstartup import KStartupCollector

n = KStartupCollector().run()
print("kstartup run() processed:", n)

db = SessionLocal()
total = db.scalar(sa.text("SELECT count(*) FROM opportunities WHERE source='kstartup'"))
openc = db.scalar(sa.text("SELECT count(*) FROM opportunities WHERE source='kstartup' AND status='open'"))
print(f"kstartup opportunities: total={total} open={openc}")
rows = db.execute(sa.text(
    "SELECT title, agency, status FROM opportunities WHERE source='kstartup' "
    "AND status='open' ORDER BY created_at DESC LIMIT 4"
)).fetchall()
for r in rows:
    print("  -", (r.title or "")[:46], "|", r.agency, "|", r.status)
db.close()
