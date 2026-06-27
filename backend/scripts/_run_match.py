# -*- coding: utf-8 -*-
"""run_daily 동기 실행 + 소스 분포/ K-Startup 매칭 유입 확인."""
from __future__ import annotations

import io
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import sqlalchemy as sa

from app.db.base import SessionLocal
from app.services.matching.tasks import run_daily

t0 = time.time()
result = run_daily()
print("run_daily result:", result, f"({time.time() - t0:.0f}s)")

db = SessionLocal()
print("\n=== matches 소스 분포 (전체) ===")
rows = db.execute(sa.text(
    "SELECT o.source, count(*) AS n FROM matches m "
    "JOIN opportunities o ON o.id = m.opportunity_id "
    "GROUP BY o.source ORDER BY n DESC"
)).fetchall()
for r in rows:
    print(f"  {r.source:<22} {r.n}")

print("\n=== K-Startup 매칭을 받은 회사 ===")
rows = db.execute(sa.text(
    "SELECT c.name, count(*) AS n, max(m.score) AS top FROM matches m "
    "JOIN opportunities o ON o.id = m.opportunity_id "
    "JOIN companies c ON c.id = m.company_id "
    "WHERE o.source='kstartup' GROUP BY c.name ORDER BY top DESC"
)).fetchall()
if not rows:
    print("  (없음 — K-Startup이 어떤 회사의 상위 추천에도 들지 못함)")
for r in rows:
    print(f"  {r.name:<24} matches={r.n} top_score={r.top:.3f}")

print("\n=== K-Startup 매칭 샘플 (상위 5) ===")
rows = db.execute(sa.text(
    "SELECT c.name AS company, o.title, m.score FROM matches m "
    "JOIN opportunities o ON o.id = m.opportunity_id "
    "JOIN companies c ON c.id = m.company_id "
    "WHERE o.source='kstartup' ORDER BY m.score DESC LIMIT 5"
)).fetchall()
for r in rows:
    print(f"  [{r.score:.3f}] {r.company} ← {(r.title or '')[:42]}")
db.close()
