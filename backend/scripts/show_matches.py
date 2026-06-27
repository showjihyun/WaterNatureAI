"""Match 결과 출력 스크립트."""
import os, sys, json
from pathlib import Path
from datetime import datetime, timezone

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

os.environ["EMBEDDING_PROVIDER"] = "bge"
os.environ["MATCH_THRESHOLD"] = "5"

from app.db.base import SessionLocal
from app.db.models.opportunity import Opportunity, Match
from app.db.models.accounts import Company
from sqlalchemy import select

db = SessionLocal()

company = db.scalar(select(Company).where(Company.name == "(주)테스트공간정보"))
if not company:
    print("ERROR: company not found")
    sys.exit(1)

matches = db.scalars(
    select(Match).where(Match.company_id == company.id).order_by(Match.score.desc()).limit(5)
).all()

print(f"Total matches top-5: {len(matches)}")
print()

for i, m in enumerate(matches, 1):
    opp = db.get(Opportunity, m.opportunity_id)
    if not opp:
        continue
    now_utc = datetime.now(timezone.utc)
    d_day = (opp.deadline.date() - now_utc.date()).days if opp.deadline else None
    d_str = f"D{d_day:+d}" if d_day is not None else "D-day n/a"
    budget = f"{opp.budget_amount:,}원" if opp.budget_amount else "null(미제공)"
    reason_str = m.reason if m.reason else "(empty)"
    risk_str = m.risk if m.risk else "없음"
    url_str = opp.detail_url if opp.detail_url else "null"

    print(f"[{i}] {opp.title[:60]}")
    print(f"    기관:     {opp.agency}")
    print(f"    분류:     {opp.category}")
    print(f"    예산:     {budget}")
    print(f"    마감:     {str(opp.deadline)[:16] if opp.deadline else 'null'} ({d_str})")
    print(f"    source:   {opp.source}")
    print(f"    score:    {m.score}")
    print(f"    reasons:  {reason_str}")
    print(f"    subscore: {json.dumps(m.subscore, ensure_ascii=False)}")
    print(f"    risk:     {risk_str}")
    print(f"    URL:      {url_str}")
    print(f"    is_canonical: {opp.is_canonical}")
    print()

# Check RecommendationItem schema
print("=" * 60)
print("RecommendationItem 스키마 필드:")
from app.schemas.opportunity import RecommendationItem
fields = list(RecommendationItem.model_fields.keys())
print(f"  {fields}")
has_url = "detail_url" in fields
print(f"  detail_url 포함: {has_url}")
if not has_url:
    print("  *** BUG: detail_url 스키마 누락 -- CTA 버튼 불가 ***")

db.close()
print("\nDone.")
