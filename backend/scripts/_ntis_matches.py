# -*- coding: utf-8 -*-
"""NTIS 매칭을 받은 회사 + 로그인 이메일 + 샘플."""
from __future__ import annotations

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import sqlalchemy as sa

from app.db.base import SessionLocal

db = SessionLocal()
print("=== NTIS 매칭을 받은 회사 (로그인 이메일 포함) ===")
rows = db.execute(sa.text(
    "SELECT c.name, u.email, count(*) AS n, max(m.score) AS top "
    "FROM matches m JOIN opportunities o ON o.id=m.opportunity_id "
    "JOIN companies c ON c.id=m.company_id "
    "LEFT JOIN users u ON u.company_id=c.id "
    "WHERE o.source='ntis' GROUP BY c.name, u.email ORDER BY top DESC"
)).fetchall()
for r in rows:
    print(f"  {r.name:<20} {r.email:<28} matches={r.n} top={r.top:.1f}")

print("\n=== NTIS 매칭 샘플 (상위 8) ===")
rows = db.execute(sa.text(
    "SELECT c.name AS company, o.title, m.score FROM matches m "
    "JOIN opportunities o ON o.id=m.opportunity_id "
    "JOIN companies c ON c.id=m.company_id "
    "WHERE o.source='ntis' ORDER BY m.score DESC LIMIT 8"
)).fetchall()
for r in rows:
    print(f"  [{r.score:.1f}] {r.company} ← {(r.title or '')[:46]}")
db.close()
