"""직접 수집 스크립트 - Celery 없이 동기 실행."""
import os, sys
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

os.environ["EMBEDDING_PROVIDER"] = "bge"
os.environ["EMBEDDING_MODEL"] = "intfloat/multilingual-e5-large"
os.environ["MATCH_THRESHOLD"] = "15"

from app.services.collectors.narajangter import NarajangterCollector
from app.services.collectors.base import _Window
from app.db.base import SessionLocal
from app.db.models.opportunity import Source, Opportunity, SourceIngestionState
from datetime import datetime, timedelta, timezone
import sqlalchemy as sa

db = SessionLocal()

# Reset ingestion state
state = db.get(SourceIngestionState, "narajangter")
if state:
    state.last_success_at = None
    state.last_status = None
    db.commit()

now = datetime.now(timezone.utc)
window = _Window(
    begin=now - timedelta(days=3),
    end=now,
)
print(f"Window: {window.begin.strftime('%Y-%m-%d')} to {window.end.strftime('%Y-%m-%d')}")

collector = NarajangterCollector()
total = 0
errors = 0

print("Fetching (yongyeok, 1 page)...")
page_done = False
for page_items in collector.iter_pages(window):
    if not page_items:
        continue
    category = page_items[0].get("_category", "?")
    print(f"  Page: {len(page_items)} items, category={category}")

    if category != "용역":
        continue

    if page_done:
        break
    page_done = True

    for raw in page_items[:50]:
        try:
            dto = collector.parse_item(raw)
            res = collector._upsert(db, dto)
            total += 1
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"    ERROR: {e}")
    break

# Update state
state = db.get(SourceIngestionState, "narajangter")
if state:
    state.last_status = "success"
    state.last_success_at = now
    state.collected_count = total
db.commit()

print(f"\nDone: {total} upserted, {errors} errors")

# Check DB
opp_count = db.scalar(sa.text("SELECT COUNT(*) FROM opportunities WHERE source='narajangter'"))
open_count = db.scalar(sa.text("SELECT COUNT(*) FROM opportunities WHERE source='narajangter' AND status='open'"))
print(f"DB: total={opp_count}, open={open_count}")

rows = db.execute(sa.text(
    "SELECT title, agency, category, budget_amount, deadline, status, detail_url, region FROM opportunities WHERE source='narajangter' ORDER BY created_at DESC LIMIT 5"
)).fetchall()

print("\nSample opportunities:")
for i, r in enumerate(rows, 1):
    budget = f"{r.budget_amount:,}" if r.budget_amount else "null"
    deadline = str(r.deadline)[:16] if r.deadline else "null"
    print(f"  [{i}] {r.title[:55]}")
    print(f"      agency={r.agency}")
    print(f"      cat={r.category}, budget={budget}, deadline={deadline}, status={r.status}, region={r.region}")
    print(f"      url={r.detail_url[:70] if r.detail_url else None}")

db.close()
print("Done.")
