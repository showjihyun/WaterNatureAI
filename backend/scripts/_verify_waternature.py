# -*- coding: utf-8 -*-
"""WaterNature 온보딩 결과 검증 — 문서 추출 + Company Context + 매칭."""
from __future__ import annotations

import io
import json
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import sqlalchemy as sa

from app.db.base import SessionLocal

db = SessionLocal()
row = db.execute(sa.text(
    "SELECT id, name, onboarding_status, document_filename, "
    "length(document_text) AS doc_len FROM companies WHERE name='WaterNature' "
    "ORDER BY created_at DESC LIMIT 1"
)).fetchone()
print("=== WaterNature company ===")
print(f"id={row.id} status={row.onboarding_status} doc={row.document_filename} doc_len={row.doc_len}")

cc = db.execute(sa.text(
    "SELECT context_json FROM company_contexts WHERE company_id=:cid "
    "ORDER BY created_at DESC LIMIT 1"
), {"cid": str(row.id)}).fetchone()
print("\n=== Company Context (LLM 추출: 프로필 최소입력 + PDF) ===")
if cc:
    ctx = cc.context_json
    for k in ["industry", "technologies", "services", "customers", "certifications",
              "regions", "strengths", "keywords"]:
        v = ctx.get(k)
        print(f"  {k}: {json.dumps(v, ensure_ascii=False)}")
    tr = ctx.get("track_records") or []
    print(f"  track_records: {len(tr)}건")
    for t in tr[:4]:
        print(f"    - {json.dumps(t, ensure_ascii=False)}")
else:
    print("  (아직 company_context 없음)")

mcount = db.scalar(sa.text(
    "SELECT count(*) FROM matches WHERE company_id=:cid"
), {"cid": str(row.id)})
print(f"\n=== 매칭 현황: {mcount}건 ===")
rows = db.execute(sa.text(
    "SELECT o.source, o.title, m.score FROM matches m "
    "JOIN opportunities o ON o.id=m.opportunity_id "
    "WHERE m.company_id=:cid ORDER BY m.score DESC LIMIT 8"
), {"cid": str(row.id)}).fetchall()
for r in rows:
    print(f"  [{r.score:.1f}] ({r.source}) {(r.title or '')[:48]}")
db.close()
