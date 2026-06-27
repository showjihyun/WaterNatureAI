"""임베딩 + 매칭 스크립트 - Celery 없이 동기 실행.
fastembed 0.8.0에서 BAAI/bge-m3 미지원 → intfloat/multilingual-e5-large (1024dim, 한국어) 사용.
"""
import os, sys, uuid, json
from pathlib import Path
from datetime import datetime, timezone

BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

os.environ["EMBEDDING_PROVIDER"] = "bge"
os.environ["EMBEDDING_MODEL"] = "intfloat/multilingual-e5-large"
os.environ["EMBEDDING_DIM"] = "1024"
os.environ["EMBEDDING_VERSION"] = "multilingual-e5-large:v1"
os.environ["MATCH_THRESHOLD"] = "15"

from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models.opportunity import Opportunity, Match
from app.db.models.accounts import Company
from app.db.models.company_context import CompanyContext
from app.services.embedding import vectorstore
import sqlalchemy as sa
from sqlalchemy import select

# ── 1. BGE 임베딩 provider (실제 모델) ────────────────────────────────────────
print("[EMBED+MATCH] 임베딩 모델 로드...")
from fastembed import TextEmbedding

model = TextEmbedding("intfloat/multilingual-e5-large")

def embed(text: str) -> list[float]:
    vecs = list(model.embed([text]))
    return list(map(float, vecs[0]))

test_vec = embed("공간정보 시스템 구축")
print(f"  OK: 차원={len(test_vec)}, 첫 값={test_vec[0]:.6f}")

db = SessionLocal()

# ── 2. CompanyContext 임베딩 ───────────────────────────────────────────────────
print("\n[EMBED] CompanyContext 임베딩...")
cc_rows = db.scalars(
    select(CompanyContext).where(CompanyContext.embedding.is_(None))
).all()
print(f"  대상: {len(cc_rows)}건")
for cc in cc_rows:
    text = str(cc.context_json)
    vec = embed(text)
    vectorstore.store_embedding(db, vectorstore.COMPANY_CONTEXTS, str(cc.id), vec)
    cc.embedded_hash = cc.content_hash
    cc.embedding_version = settings.embedding_version
    cc.embedded_at = datetime.now(timezone.utc)
db.commit()
print(f"  OK: {len(cc_rows)}건 임베딩 완료")

# ── 3. Opportunity 임베딩 (status=open, narajangter) ─────────────────────────
print("\n[EMBED] Opportunity 임베딩...")
opps = db.scalars(
    select(Opportunity).where(
        Opportunity.source == "narajangter",
        Opportunity.status == "open",
        Opportunity.embedding.is_(None),
    )
).all()
print(f"  대상: {len(opps)}건")
EMBEDDED_COUNT = 0
for opp in opps:
    parts = [f"[{opp.category}] {opp.title}" if opp.category else opp.title]
    if opp.agency:
        parts.append(f"발주/소관: {opp.agency}")
    if opp.region:
        parts.append(f"지역: {opp.region}")
    if opp.description:
        parts.append(opp.description)
    text = "\n".join(parts)
    vec = embed(text)
    vectorstore.store_embedding(db, vectorstore.OPPORTUNITIES, str(opp.id), vec)
    opp.embedded_hash = opp.content_hash
    opp.embedding_version = settings.embedding_version
    opp.embedded_at = datetime.now(timezone.utc)
    EMBEDDED_COUNT += 1
db.commit()
print(f"  OK: {EMBEDDED_COUNT}건 임베딩 완료")

# ── 4. 매칭 run_daily ──────────────────────────────────────────────────────────
print("\n[MATCH] run_daily 실행 (규칙 기반, LLM off)...")
from app.services.matching.tasks import run_daily

match_result = run_daily(_llm_fn=None)
print(f"  결과: {match_result}")

# ── 5. matches 직접 조회 ──────────────────────────────────────────────────────
print("\n[RESULTS] Matches 조회 (상위 5)...")
# 회사 찾기
company = db.scalar(select(Company).where(Company.name == "(주)테스트공간정보"))
if not company:
    print("  ERROR: 테스트 회사 없음")
    db.close()
    sys.exit(1)

matches = db.scalars(
    select(Match)
    .where(Match.company_id == company.id)
    .order_by(Match.score.desc())
    .limit(5)
).all()

print(f"  matches 건수(상위 5): {len(matches)}")
print()

results = []
for i, m in enumerate(matches, 1):
    opp = db.get(Opportunity, m.opportunity_id)
    if not opp:
        continue
    now_utc = datetime.now(timezone.utc)
    d_day = (opp.deadline.date() - now_utc.date()).days if opp.deadline else None
    d_str = f"D{d_day:+d}" if d_day is not None else "D-day 미상"
    budget = f"{opp.budget_amount:,}원" if opp.budget_amount else "null(미제공)"

    print(f"  [{i}] {opp.title[:60]}")
    print(f"      기관:    {opp.agency or 'null'}")
    print(f"      분류:    {opp.category or 'null'}")
    print(f"      예산:    {budget}")
    print(f"      마감:    {str(opp.deadline)[:16] if opp.deadline else 'null'} ({d_str})")
    print(f"      score:   {m.score}")
    print(f"      reasons: {m.reason or '(빈값)'}")
    print(f"      subscore:{m.subscore}")
    print(f"      risk:    {m.risk or '없음'}")
    print(f"      URL:     {opp.detail_url or 'null'}")
    print()

    results.append({
        "title": opp.title,
        "agency": opp.agency,
        "category": opp.category,
        "budget_amount": opp.budget_amount,
        "deadline": str(opp.deadline) if opp.deadline else None,
        "d_day": d_day,
        "score": m.score,
        "reason": m.reason,
        "subscore": m.subscore,
        "risk": m.risk,
        "detail_url": opp.detail_url,
        "source": opp.source,
        "is_canonical": opp.is_canonical,
    })

# ── 6. 추가 통계 ──────────────────────────────────────────────────────────────
null_budget = sum(1 for r in results if r["budget_amount"] is None)
null_deadline = sum(1 for r in results if r["deadline"] is None)
null_reasons = sum(1 for r in results if not r["reason"])
null_url = sum(1 for r in results if not r["detail_url"])
total = len(results)

if total > 0:
    print("=" * 60)
    print("[UX/UI 정보 충실도 — match 상위 5 기준]")
    print(f"  budget_amount null: {null_budget}/{total}")
    print(f"  deadline null:      {null_deadline}/{total}")
    print(f"  reasons 빈값:       {null_reasons}/{total}")
    print(f"  detail_url null:    {null_url}/{total}")

    # detail_url이 RecommendationItem 스키마에 없음 확인
    print("\n[스키마 확인] RecommendationItem 필드:")
    from app.schemas.opportunity import RecommendationItem
    import inspect
    fields = list(RecommendationItem.model_fields.keys())
    print(f"  필드: {fields}")
    has_url = "detail_url" in fields
    print(f"  detail_url 포함: {has_url}")
    if not has_url:
        print("  *** BUG: detail_url 스키마 누락 — CTA 버튼 불가 ***")

db.close()
print("\n완료.")
