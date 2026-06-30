# -*- coding: utf-8 -*-
"""기존 공고 industry(KSIC 표준 업종) 백필 — 1회성. 읽기→룰 분류→bulk update.

실행: python scripts/_backfill_industry.py        (industry IS NULL 만, 재실행 안전)
      python scripts/_backfill_industry.py --all   (전체 재분류; 룰 변경 후 갱신용)
"""
from __future__ import annotations

import collections
import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models.opportunity import Opportunity
from app.services.ksic import classify_industry, ksic_name


def main(only_null: bool = True) -> None:
    db = SessionLocal()
    try:
        q = select(
            Opportunity.id, Opportunity.title, Opportunity.description,
            Opportunity.source, Opportunity.category,
        )
        if only_null:
            q = q.where(Opportunity.industry.is_(None))
        rows = db.execute(q).all()
        print(f"대상 {len(rows)}건 ({'NULL만' if only_null else '전체'}) 분류 중...")

        updates: list[dict] = []
        dist: collections.Counter = collections.Counter()
        for r in rows:
            code = classify_industry(r.title, r.description, r.source, r.category)
            updates.append({"id": r.id, "industry": code})
            dist[code] += 1

        batch = 1000
        for i in range(0, len(updates), batch):
            db.bulk_update_mappings(Opportunity, updates[i:i + batch])
            db.commit()
            print(f"  커밋 {min(i + batch, len(updates))}/{len(updates)}")

        total = sum(dist.values()) or 1
        print("=== 백필 분포 ===")
        for code, n in dist.most_common():
            print(f"  {code:4} {(ksic_name(code) or ''):24} {n:6} ({100 * n // total}%)")
    finally:
        db.close()


if __name__ == "__main__":
    main(only_null="--all" not in sys.argv)
