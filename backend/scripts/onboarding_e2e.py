# -*- coding: utf-8 -*-
"""온보딩 -> 추천 전체 E2E 검증 (API 경유 + 동기 보강).

이전 e2e_check.py와의 차이: register/profile/brain 을 **실제 HTTP 엔드포인트**
(FastAPI TestClient)로 통과시켜 company 라우터(profile/brain)를 포함한
풀 API 흐름을 증명한다. Celery 워커가 없으므로 embed/run_daily 는 스크립트에서
동기 직접 호출로 보강한다.

실행 (backend/ 에서):
    python scripts/onboarding_e2e.py

전제:
- docker compose -f docker-compose.dev.yml up -d --wait postgres  (host 5433)
- alembic upgrade head 완료
- .env: EMBEDDING_PROVIDER=bge, EMBEDDING_MODEL=intfloat/multilingual-e5-large,
        MATCH_THRESHOLD=45, NARAJANGTER_SERVICE_KEY=<실키>
- fastembed e5-large 모델 캐시 (FASTEMBED_CACHE_PATH=/tmp/fastembed_cache).

가드레일:
- 검증 전용. 프로덕션 코드 수정 없음. 외부 호출 = 나라장터 수집(소규모) + e5 임베딩만.
- 모델 다운로드/네트워크 막히면 정직 보고(가짜 벡터 금지).
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── backend/ 를 sys.path / cwd 로 ────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# fastembed e5-large 캐시 경로 (이전 E2E 가 여기에 다운로드해 둠). 없으면 첫 호출 시 다운로드.
os.environ.setdefault("FASTEMBED_CACHE_PATH", "/tmp/fastembed_cache")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import select  # noqa: E402

SEP = "=" * 72


def banner(title: str) -> None:
    print("\n" + SEP)
    print(title)
    print(SEP)


banner("BizRadar AI -- 온보딩->추천 E2E (API 경유 + 동기 보강)")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 0: 환경/설정 확인
# ─────────────────────────────────────────────────────────────────────────────
print("\n[STEP 0] 환경/설정 확인...")
try:
    import fastembed  # noqa: F401
    print(f"  fastembed: {fastembed.__version__}")
except ImportError:
    print("  ERROR: fastembed 미설치 (`pip install fastembed`)")
    sys.exit(1)

from app.core.config import settings  # noqa: E402

print(f"  DATABASE_URL:      {settings.database_url}")
print(f"  EMBEDDING_PROVIDER:{settings.embedding_provider}")
print(f"  EMBEDDING_MODEL:   {settings.embedding_model}")
print(f"  EMBEDDING_DIM:     {settings.embedding_dim}")
print(f"  MATCH_THRESHOLD:   {settings.match_threshold}")
print(f"  FASTEMBED_CACHE:   {os.environ.get('FASTEMBED_CACHE_PATH')}")
key = settings.narajangter_service_key
print(f"  NARAJANGTER_KEY:   {'<set:' + key[:10] + '...>' if key else '<MISSING>'}")
if not key:
    print("  ERROR: NARAJANGTER_SERVICE_KEY 미설정 — 실수집 불가")
    sys.exit(1)

from app.db.base import SessionLocal, get_engine  # noqa: E402

try:
    with get_engine().connect() as conn:
        row = conn.execute(sa.text("SELECT current_database(), version()")).fetchone()
    print(f"  DB OK: db={row[0]}, {row[1][:50]}...")
except Exception as exc:  # noqa: BLE001
    print(f"  ERROR: DB 연결 실패: {exc}")
    print("  docker compose -f docker-compose.dev.yml up -d --wait postgres 필요")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# 사전 정리: 재실행 안전 (테스트 유저/회사/컨텍스트/매칭/액션 삭제)
# ─────────────────────────────────────────────────────────────────────────────
TEST_EMAIL = "onboarding_e2e@bizradar-e2e.co.kr"
TEST_PASSWORD = "OnboardPass123!"
COMPANY_NAME = "(주)지오스페이스랩"

from app.db.models.accounts import Company, NotificationSetting, RefreshToken, User  # noqa: E402
from app.db.models.company_context import CompanyContext  # noqa: E402
from app.db.models.opportunity import Match, Opportunity, UserOpportunityAction  # noqa: E402

print("\n  사전 정리(재실행 안전)...")
_db = SessionLocal()
try:
    u = _db.scalar(select(User).where(User.email == TEST_EMAIL))
    if u:
        cid = u.company_id
        _db.execute(sa.delete(RefreshToken).where(RefreshToken.user_id == u.id))
        if cid:
            _db.execute(sa.delete(UserOpportunityAction).where(UserOpportunityAction.company_id == cid))
            _db.execute(sa.delete(Match).where(Match.company_id == cid))
            _db.execute(sa.delete(CompanyContext).where(CompanyContext.company_id == cid))
            _db.execute(sa.delete(NotificationSetting).where(NotificationSetting.company_id == cid))
        _db.delete(u)
        _db.commit()
        if cid:
            c = _db.get(Company, cid)
            if c:
                _db.delete(c)
                _db.commit()
        print("  OK: 기존 테스트 데이터 삭제")
    else:
        print("  (정리 대상 없음)")

    # 단일 패스 데모를 위해 이전 수집 공고 제거(매번 fresh collect+embed 증명).
    from app.db.models.opportunity import OpportunityChange  # noqa: PLC0415
    opp_ids = [r0 for r0 in _db.scalars(
        select(Opportunity.id).where(Opportunity.source == "narajangter")
    ).all()]
    if opp_ids:
        _db.execute(sa.delete(OpportunityChange).where(OpportunityChange.opportunity_id.in_(opp_ids)))
        _db.execute(sa.delete(UserOpportunityAction).where(UserOpportunityAction.opportunity_id.in_(opp_ids)))
        _db.execute(sa.delete(Match).where(Match.opportunity_id.in_(opp_ids)))
        _db.execute(sa.delete(Opportunity).where(Opportunity.id.in_(opp_ids)))
        _db.commit()
        print(f"  OK: 이전 나라장터 공고 {len(opp_ids)}건 제거(fresh collect)")
finally:
    _db.close()

# ─────────────────────────────────────────────────────────────────────────────
# TestClient 준비
# ─────────────────────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=True)
API = settings.api_v1_prefix

REPORT: dict = {}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: 회원가입 (API)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 1] 회원가입 POST /auth/register (API)")
r = client.post(f"{API}/auth/register", json={
    "email": TEST_EMAIL, "password": TEST_PASSWORD, "company_name": COMPANY_NAME,
})
print(f"  status={r.status_code}")
if r.status_code != 201:
    print(f"  ERROR: {r.text[:300]}")
    sys.exit(1)
tokens = r.json()
ACCESS = tokens["access_token"]
REFRESH = tokens["refresh_token"]
print(f"  OK: access_token 획득(len={len(ACCESS)}), token_type={tokens.get('token_type')}")
H = {"Authorization": f"Bearer {ACCESS}"}
REPORT["register"] = {"status": r.status_code, "has_token": bool(ACCESS)}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: 프로필 입력 (API, company 라우터) — IT/SI/공간정보
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 2] 프로필 PUT /company/profile (API)")
profile_body = {
    "industry": "공간정보",
    "region": "전국",
    "description": (
        "GIS 기반 공간정보 시스템 구축 및 SI 전문 기업. 디지털트윈, 측량, "
        "지리정보 데이터 처리, 공간정보 플랫폼 개발 및 정보화 사업 수행."
    ),
    "phone": "02-1234-5678",
}
r = client.put(f"{API}/company/profile", headers=H, json=profile_body)
print(f"  PUT status={r.status_code}")
if r.status_code != 200:
    print(f"  ERROR: {r.text[:300]}")
    sys.exit(1)
prof = r.json()
print(f"  OK: industry={prof.get('industry')}, region={prof.get('region')}")
print(f"      onboarding_status(전이 후)={prof.get('onboarding_status')}  (기대: document)")

# GET 으로 반영 확인
r2 = client.get(f"{API}/company/profile", headers=H)
print(f"  GET /company/profile status={r2.status_code}")
prof_get = r2.json()
print(f"      반영확인: industry={prof_get.get('industry')}, status={prof_get.get('onboarding_status')}")
REPORT["profile"] = {
    "put_status": r.status_code,
    "onboarding_status_after_put": prof.get("onboarding_status"),
    "get_status": r2.status_code,
    "industry": prof_get.get("industry"),
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Company Brain (API) — context 생성 + status 'ready'
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 3] Company Brain POST /company/brain (API)")
r = client.post(f"{API}/company/brain", headers=H)
print(f"  status={r.status_code}")
if r.status_code != 200:
    print(f"  ERROR: {r.text[:300]}")
    sys.exit(1)
brain = r.json()
CC_ID = brain["company_context_id"]
print(f"  OK: company_context_id={CC_ID}")
print(f"      onboarding_status={brain.get('onboarding_status')}  (기대: ready)")

# context_json 확인 (규칙 매칭 신호 점검)
_db = SessionLocal()
try:
    cc = _db.get(CompanyContext, uuid.UUID(CC_ID))
    ctx_json = cc.context_json
    print(f"      context.industry={ctx_json.get('industry')}")
    print(f"      context.regions={ctx_json.get('regions')}")
    print(f"      context.keywords={ctx_json.get('keywords')}")
finally:
    _db.close()
REPORT["brain"] = {
    "status": r.status_code,
    "cc_id": CC_ID,
    "onboarding_status": brain.get("onboarding_status"),
    "keywords": ctx_json.get("keywords"),
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: 회사 임베딩 (동기 보강) — embed_company_context 직접 호출 (Celery 워커 없음)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 4] 회사 임베딩 embed_company_context (동기 보강, 실 e5)")
from app.services.embedding.tasks import embed_company_context  # noqa: E402

try:
    # bind=True Celery task -> .run() 으로 self 바인딩하여 동기 호출
    embed_company_context.run(CC_ID)
    _db = SessionLocal()
    try:
        cc = _db.get(CompanyContext, uuid.UUID(CC_ID))
        has_emb = cc.embedding is not None
        dim = len(cc.embedding) if has_emb else 0
    finally:
        _db.close()
    print(f"  OK: company_context.embedding 채움 = {has_emb}, dim={dim}")
    REPORT["company_embedding"] = {"ok": has_emb, "dim": dim}
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: 회사 임베딩 실패: {exc}")
    traceback.print_exc()
    REPORT["company_embedding"] = {"ok": False, "error": str(exc)}
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: 실 수집 (소규모: 최근 3일, 용역 1유형, 1페이지)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 5] 나라장터 실 수집 (소규모: 용역 1유형, 최근 3일, 1페이지)")
from app.services.collectors.base import _Window  # noqa: E402
from app.services.collectors.narajangter import NarajangterCollector  # noqa: E402
from app.db.models.opportunity import Source  # noqa: E402

now_utc = datetime.now(timezone.utc)
window = _Window(begin=now_utc - timedelta(days=3), end=now_utc)
print(f"  윈도우: {window.begin:%Y-%m-%d} ~ {window.end:%Y-%m-%d}")


# 주: collector.run() 은 변경분마다 embed_opportunity.delay() 를 호출하는데, Celery/Redis
# 미연결 시 .delay() 가 예외를 던지고 run() 의 except 가 트랜잭션을 rollback → upsert 유실.
# 따라서 run() 대신 iter_pages → _upsert 를 직접 구동(검증 스크립트 동기 보강). 임베딩은 STEP 6.
_db = SessionLocal()
COLLECTED = 0
OPEN_OPPS = 0
try:
    if _db.get(Source, "narajangter") is None:
        _db.add(Source(code="narajangter", name="나라장터(조달청) 입찰공고",
                       tier=0, collector="narajangter", enabled=True))
        _db.commit()
finally:
    _db.close()

MAX_ITEMS = 30  # 검증용 소규모 상한
try:
    collector = NarajangterCollector()
    _db = SessionLocal()
    try:
        done_servc_page = False
        for page_items in collector.iter_pages(window):
            if not page_items:
                continue
            cat = page_items[0].get("_category")
            if cat != "용역":  # 용역 1유형만
                continue
            if done_servc_page:
                break
            done_servc_page = True
            for raw in page_items[:MAX_ITEMS]:
                dto = collector.parse_item(raw)
                collector._upsert(_db, dto)  # noqa: SLF001 (검증 스크립트 동기 보강)
                COLLECTED += 1
            break  # 1페이지만
        print(f"  OK: 수집 upsert 처리 건수 = {COLLECTED}")
    finally:
        _db.close()
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: 수집 실패: {exc}")
    traceback.print_exc()

_db = SessionLocal()
try:
    total = _db.scalar(sa.text("SELECT COUNT(*) FROM opportunities WHERE source='narajangter'"))
    OPEN_OPPS = _db.scalar(sa.text(
        "SELECT COUNT(*) FROM opportunities WHERE source='narajangter' AND status='open'"))
    print(f"  DB 공고: total={total}, open={OPEN_OPPS}")
    sample = _db.execute(sa.text(
        "SELECT title, agency, category, budget_amount, deadline, status, region "
        "FROM opportunities WHERE source='narajangter' ORDER BY created_at DESC LIMIT 3"
    )).fetchall()
    for i, s in enumerate(sample, 1):
        b = f"{s.budget_amount:,}" if s.budget_amount else "null"
        print(f"    [{i}] {s.title[:45]} | {s.agency} | {s.category} | 예산={b} | region={s.region} | {s.status}")
finally:
    _db.close()
REPORT["collect"] = {"processed": COLLECTED, "open_opps": OPEN_OPPS}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: 공고 임베딩 (동기) — embed_opportunity 직접 호출 (Celery 워커 없음)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 6] 공고 임베딩 embed_opportunity (동기, 실 e5)")
from app.services.embedding.tasks import embed_opportunity  # noqa: E402

EMBEDDED = 0
_db = SessionLocal()
try:
    open_ids = _db.scalars(
        select(Opportunity.id).where(
            Opportunity.source == "narajangter",
            Opportunity.status == "open",
            Opportunity.embedding.is_(None),
        )
    ).all()
finally:
    _db.close()
print(f"  임베딩 대상(open, embedding NULL): {len(open_ids)}건")
try:
    for oid in open_ids:
        embed_opportunity.run(str(oid))  # bind=True -> .run()
        EMBEDDED += 1
    print(f"  OK: 공고 임베딩 = {EMBEDDED}건")
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: 공고 임베딩 실패: {exc}")
    traceback.print_exc()
REPORT["opp_embedding"] = {"embedded": EMBEDDED}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: 매칭 (동기) — run_daily(_llm_fn=None) 직접 호출 (규칙 기반)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 7] 매칭 run_daily(_llm_fn=None) (동기, 규칙, LLM off)")
from app.services.matching.tasks import run_daily  # noqa: E402

try:
    match_result = run_daily(_llm_fn=None)
    print(f"  OK: {match_result}  (threshold={settings.match_threshold})")
    REPORT["matching"] = match_result
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: run_daily 실패: {exc}")
    traceback.print_exc()
    REPORT["matching"] = {"error": str(exc)}

# 투명성: 후보 공고별 규칙 점수 진단(임계 미달이어도 분포/근거를 정직 보고).
# read-only — 엔진 스코어러를 그대로 사용(프로덕션 변경 아님).
print("\n  ── 후보 규칙 점수 진단 (threshold 필터 전, Top by score) ─────")
from app.services.matching.engine import (  # noqa: E402
    _compute_rule_presets, retrieve_candidates, score_match,
)

CAND_DIAG: list[dict] = []
_db = SessionLocal()
try:
    cand_ids = retrieve_candidates(_db, CC_ID)
    omap = {
        str(o.id): o
        for o in _db.scalars(
            select(Opportunity).where(Opportunity.id.in_([uuid.UUID(c) for c in cand_ids]))
        ).all()
    }
    for cid in cand_ids:
        o = omap.get(cid)
        if o is None:
            continue
        od = {"id": str(o.id), "title": o.title or "", "agency": o.agency,
              "region": o.region, "category": o.category, "description": o.description}
        res = score_match(ctx_json, od, _compute_rule_presets(ctx_json, od), llm_complete_json=None)
        CAND_DIAG.append({"score": res.score, "subscore": res.subscore,
                          "title": o.title, "reasons": res.reasons})
    CAND_DIAG.sort(key=lambda x: x["score"], reverse=True)
    for d in CAND_DIAG:
        mark = "  <== >=THRESHOLD" if d["score"] >= settings.match_threshold else ""
        print(f"    score={d['score']:3d}{mark} sub={d['subscore']}")
        print(f"        {d['title'][:54]}")
        print(f"        reasons={d['reasons']}")
finally:
    _db.close()
REPORT["candidate_diagnostic"] = CAND_DIAG

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: 추천 조회 + 풀 API 흐름 (recommendations / opportunities / actions / stats)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 8] 추천 조회 + 풀 API 흐름 (API)")

# 8-1) GET /recommendations/today
r = client.get(f"{API}/recommendations/today", headers=H)
print(f"\n  GET /recommendations/today -> {r.status_code}")
RECS = r.json() if r.status_code == 200 else []
print(f"  추천 건수 = {len(RECS)}")
REPORT["recommendations"] = {"status": r.status_code, "count": len(RECS), "items": RECS}

if RECS:
    print("\n  ── 추천 Top (실제) ─────────────────────────────────────────")
    for i, it in enumerate(RECS, 1):
        b = f"{it['budget_amount']:,}원" if it.get("budget_amount") else "null(미제공)"
        dd = it.get("d_day")
        dd_s = f"D{dd:+d}" if dd is not None else "D-day 미상"
        print(f"  [{i}] {it['title'][:58]}")
        print(f"      기관: {it.get('agency') or 'null'} | 분류: {it.get('category') or 'null'}")
        print(f"      예산: {b} | 마감: {str(it.get('deadline'))[:16] if it.get('deadline') else 'null'} ({dd_s})")
        print(f"      score: {it.get('score')} | reasons: {it.get('reasons')}")
        print(f"      detail_url: {it.get('detail_url') or 'null'}")

# 8-2) GET /opportunities (필터 미적용 + min_score 필터)
r = client.get(f"{API}/opportunities", headers=H, params={"page": 1, "size": 20})
print(f"\n  GET /opportunities -> {r.status_code}, total={r.json().get('total') if r.status_code==200 else '?'}")
r_f = client.get(f"{API}/opportunities", headers=H, params={"min_score": settings.match_threshold})
print(f"  GET /opportunities?min_score={settings.match_threshold} -> {r_f.status_code}, "
      f"total={r_f.json().get('total') if r_f.status_code==200 else '?'}")
REPORT["opportunities_list"] = {
    "status": r.status_code,
    "total": r.json().get("total") if r.status_code == 200 else None,
}

# 8-3) POST /opportunities/{id}/actions {type: saved} (멱등) + opened
#       추천이 비어도 액션/스탯 흐름을 증명하기 위해 수집된 open 공고 1건에 대해 수행.
if RECS:
    SAVED_ID = RECS[0]["opportunity_id"]
else:
    _db = SessionLocal()
    try:
        SAVED_ID = str(_db.scalar(
            select(Opportunity.id).where(
                Opportunity.source == "narajangter", Opportunity.status == "open"
            ).limit(1)
        ))
    finally:
        _db.close()

if SAVED_ID and SAVED_ID != "None":
    ra = client.post(f"{API}/opportunities/{SAVED_ID}/actions", headers=H, json={"type": "saved"})
    ra2 = client.post(f"{API}/opportunities/{SAVED_ID}/actions", headers=H, json={"type": "saved"})  # 멱등
    ro = client.post(f"{API}/opportunities/{SAVED_ID}/actions", headers=H, json={"type": "opened"})
    print(f"\n  대상 opp={SAVED_ID[:8]}... (추천 비었으면 수집 공고로 흐름 증명)")
    print(f"  POST actions saved  -> {ra.status_code} {ra.json()} (재호출 멱등 -> {ra2.status_code})")
    print(f"  POST actions opened -> {ro.status_code} {ro.json()}")
    REPORT["actions"] = {"saved": ra.status_code, "saved_idempotent": ra2.status_code,
                         "opened": ro.status_code, "target": SAVED_ID}
else:
    print("\n  (수집 공고도 없음 -> actions 스킵)")
    REPORT["actions"] = {"skipped": True}

# 8-4) GET /dashboard/stats (saved/opened 반영 확인)
r = client.get(f"{API}/dashboard/stats", headers=H)
print(f"\n  GET /dashboard/stats -> {r.status_code}: {r.json() if r.status_code==200 else r.text[:200]}")
REPORT["stats"] = r.json() if r.status_code == 200 else {"status": r.status_code}

# 8-5) 인증/테넌트 격리
r_noauth = client.get(f"{API}/recommendations/today")
print(f"\n  [격리] GET /recommendations/today (토큰 없음) -> {r_noauth.status_code} (기대 401/403)")

# 8-6) company 스코프 격리: 다른 회사로 가입 → 첫 회사의 saved 액션이 보이면 안 됨(stats=0)
r2 = client.post(f"{API}/auth/register", json={
    "email": "other_e2e@bizradar-e2e.co.kr", "password": "OtherPass123!",
    "company_name": "(주)타사검증",
})
isolation_ok = None
if r2.status_code == 201:
    H2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    s2 = client.get(f"{API}/dashboard/stats", headers=H2).json()
    isolation_ok = (s2.get("saved", -1) == 0 and s2.get("opened", -1) == 0)
    print(f"  [격리] 타사 stats={s2} → 타사에 saved/opened 미노출: {isolation_ok}")
    # 타사 정리
    _db = SessionLocal()
    try:
        ou = _db.scalar(select(User).where(User.email == "other_e2e@bizradar-e2e.co.kr"))
        if ou:
            ocid = ou.company_id
            _db.execute(sa.delete(RefreshToken).where(RefreshToken.user_id == ou.id))
            _db.delete(ou); _db.commit()
            oc = _db.get(Company, ocid)
            if oc:
                _db.delete(oc); _db.commit()
    finally:
        _db.close()
REPORT["auth_guard"] = {"no_token_status": r_noauth.status_code, "tenant_isolation_ok": isolation_ok}

# ─────────────────────────────────────────────────────────────────────────────
# 최종 요약
# ─────────────────────────────────────────────────────────────────────────────
banner("E2E 요약")
print(f"""
  register:            status={REPORT['register']['status']}, token={REPORT['register']['has_token']}
  profile:             PUT={REPORT['profile']['put_status']} status전이={REPORT['profile']['onboarding_status_after_put']} GET={REPORT['profile']['get_status']}
  brain:               status={REPORT['brain']['status']} cc_id={REPORT['brain']['cc_id'][:8]}... onboarding={REPORT['brain']['onboarding_status']}
  회사 임베딩:          ok={REPORT['company_embedding'].get('ok')} dim={REPORT['company_embedding'].get('dim')}
  수집:                processed={REPORT['collect']['processed']} open={REPORT['collect']['open_opps']}
  공고 임베딩:          {REPORT['opp_embedding']['embedded']}건
  매칭:                {REPORT['matching']} (threshold={settings.match_threshold})
  추천:                count={REPORT['recommendations']['count']}
  actions:             {REPORT['actions']}
  stats:               {REPORT['stats']}
  인증가드(무토큰):     {REPORT['auth_guard']['no_token_status']} / 테넌트격리={REPORT['auth_guard']['tenant_isolation_ok']}
""")

# 후보 점수 분포(추천 비어도 정직 보고)
if REPORT.get("candidate_diagnostic"):
    cd = REPORT["candidate_diagnostic"]
    sc = [d["score"] for d in cd]
    print(f"  [관찰] 후보 score 분포(규칙, threshold {settings.match_threshold}): {sc}")
    print(f"         최고={max(sc)} / >=임계={sum(1 for s in sc if s>=settings.match_threshold)}건")

# 점수 분산 관찰
if RECS:
    scores = [it.get("score") for it in RECS]
    print(f"  [관찰] score 분포: {scores}")
    nb = sum(1 for it in RECS if not it.get("budget_amount"))
    nd = sum(1 for it in RECS if not it.get("deadline"))
    nu = sum(1 for it in RECS if not it.get("detail_url"))
    nr = sum(1 for it in RECS if not it.get("reasons"))
    print(f"  [관찰] 빈 필드: budget={nb}/{len(RECS)} deadline={nd}/{len(RECS)} "
          f"detail_url={nu}/{len(RECS)} reasons={nr}/{len(RECS)}")

banner("E2E 검증 완료")
