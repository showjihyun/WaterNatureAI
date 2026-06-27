# -*- coding: utf-8 -*-
"""데모/테스트 회사 로그인 이메일 조회."""
from __future__ import annotations

import io
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import sqlalchemy as sa

from app.db.base import SessionLocal

db = SessionLocal()
rows = db.execute(sa.text(
    "SELECT u.email, c.name, "
    "(SELECT count(*) FROM matches m JOIN opportunities o ON o.id=m.opportunity_id "
    " WHERE m.company_id=c.id AND o.source='kstartup') AS kstartup_n "
    "FROM users u JOIN companies c ON c.id = u.company_id "
    "ORDER BY kstartup_n DESC"
)).fetchall()
for r in rows:
    print(f"{r.email:<34} | {r.name:<22} | kstartup_matches={r.kstartup_n}")
db.close()
