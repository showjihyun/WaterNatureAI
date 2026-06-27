"""일회성: 나라장터 4유형(물품/용역/공사/외자) 넓은 윈도우 수집 → 열린 공고 임베딩 → 재매칭.

추천 다양화(소스/유형 확대)용. run()의 증분 윈도우를 우회해 최근 N일을 직접 수집한다.
실행: INGEST_MAX_PAGES=2 DATABASE_URL=...5433/bizradar PYTHONPATH=. python scripts/broaden_collect.py
(.env의 NARAJANGTER_SERVICE_KEY 자동 로드. 외부 호출=나라장터 수집 + e5 임베딩만.)
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.base import SessionLocal
from app.db.models.opportunity import Opportunity
from app.services.collectors.base import _Window
from app.services.collectors.narajangter import NarajangterCollector
from app.services.embedding.tasks import embed_opportunity
from app.services.matching.tasks import run_daily

DAYS = 10
EMBED_CAP = 600

col = NarajangterCollector()
win = _Window(
    begin=datetime.now(timezone.utc) - timedelta(days=DAYS),
    end=datetime.now(timezone.utc),
)

# ① 수집 (4유형, 직접 upsert — run() 우회로 넓은 윈도우 사용)
db = SessionLocal()
n = 0
open_by_cat: Counter[str] = Counter()
total_by_cat: Counter[str] = Counter()
try:
    for page in col.iter_pages(win):
        for raw in page:
            dto = col.parse_item(raw)
            col._upsert(db, dto)
            n += 1
            total_by_cat[dto.category or "?"] += 1
            if dto.status == "open":
                open_by_cat[dto.category or "?"] += 1
finally:
    db.close()
print(f"[collect] upserted={n} | total_by_cat={dict(total_by_cat)} | open_by_cat={dict(open_by_cat)}", flush=True)

# ② 열린 공고 중 임베딩 없는 것 임베딩 (동기)
db = SessionLocal()
ids = [
    str(o.id)
    for o in db.scalars(
        select(Opportunity).where(
            Opportunity.status == "open", Opportunity.embedding.is_(None)
        )
    ).all()
][:EMBED_CAP]
db.close()
print(f"[embed] embedding {len(ids)} open opps (cap {EMBED_CAP})...", flush=True)
for i, oid in enumerate(ids, 1):
    embed_opportunity.run(oid)
    if i % 50 == 0:
        print(f"  embedded {i}/{len(ids)}", flush=True)
print(f"[embed] done: {len(ids)}", flush=True)

# ③ 재매칭 (threshold 35)
result = run_daily()
print(f"[match] run_daily: {result}", flush=True)

# ④ 열린 공고 총계
db = SessionLocal()
open_count = len(db.scalars(select(Opportunity.id).where(Opportunity.status == "open")).all())
db.close()
print(f"[done] open opps now: {open_count}", flush=True)
