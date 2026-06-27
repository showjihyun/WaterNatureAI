# -*- coding: utf-8 -*-
"""온보딩->추천 E2E (데이터-적응 산업 선택, 매칭 개선 검증).

직전 E2E(onboarding_e2e.py)의 GIS 고정 프로필 대신, 실 수집된 공고 타이틀을
INDUSTRY_KEYWORDS 로 분석하여 가장 많이 매칭되는 산업을 자동 선택.

실행 (backend/ 에서):
    python scripts/onboarding_e2e_match.py

전제:
- docker compose -f docker-compose.dev.yml up -d --wait postgres  (host 5433)
- alembic upgrade head 완료
- .env: NARAJANGTER_SERVICE_KEY=<실키>
- fastembed e5-large 모델 캐시

가드레일:
- scripts/ 에만 작성. app/ 수정 없음.
- matched=0이면 0으로 정직 보고(억지 키워드 주입 금지).
- 산업 단위 선택만(키워드 주입 금지).
"""
from __future__ import annotations

import io
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows cp949 콘솔 인코딩 오류 방지: stdout/stderr를 UTF-8로 재설정
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ── backend/ 를 sys.path / cwd 로 ────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# MATCH_THRESHOLD 35 강제 (개선된 임계값 — .env의 45를 E2E 검증 목적으로 override)
# 프로덕션 코드(.env/app/) 수정 없음. 스크립트 내 환경변수만 조정.
os.environ["MATCH_THRESHOLD"] = "35"

# fastembed e5-large 캐시 경로
os.environ.setdefault("FASTEMBED_CACHE_PATH", "/tmp/fastembed_cache")

import sqlalchemy as sa  # noqa: E402
from sqlalchemy import select  # noqa: E402

SEP = "=" * 72


def banner(title: str) -> None:
    print("\n" + SEP)
    print(title)
    print(SEP)


banner("BizRadar AI -- 온보딩->추천 E2E v2 (데이터-적응 산업 선택)")

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

# pydantic-settings lru_cache 우회: MATCH_THRESHOLD 환경변수 설정 후 settings reload
from app.core.config import Settings  # noqa: E402
settings = Settings()  # 환경변수 MATCH_THRESHOLD=35 반영한 fresh instance

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
TEST_EMAIL = "e2e_match_v2@bizradar-e2e.co.kr"
TEST_PASSWORD = "MatchPass456!"

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

    # 이전 나라장터 공고 제거 (fresh collect+embed)
    from app.db.models.opportunity import OpportunityChange, Source  # noqa: PLC0415
    opp_ids = list(_db.scalars(
        select(Opportunity.id).where(Opportunity.source == "narajangter")
    ).all())
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
# STEP 1: 실 수집 — open 공고 30건 이상 확보 목표 (용역 다페이지, 최대 500건)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 1] 나라장터 실 수집 (용역 다페이지, open>=30 목표)")
from app.services.collectors.base import _Window  # noqa: E402
from app.services.collectors.narajangter import NarajangterCollector, _FMT, OPS  # noqa: E402

now_utc = datetime.now(timezone.utc)
COLLECT_DAYS = 14
window = _Window(begin=now_utc - timedelta(days=COLLECT_DAYS), end=now_utc)
print(f"  윈도우: {window.begin:%Y-%m-%d} ~ {window.end:%Y-%m-%d} ({COLLECT_DAYS}일)")

_db = SessionLocal()
try:
    if _db.get(Source, "narajangter") is None:
        _db.add(Source(code="narajangter", name="나라장터(조달청) 입찰공고",
                       tier=0, collector="narajangter", enabled=True))
        _db.commit()
finally:
    _db.close()

COLLECTED = 0
COLLECT_BY_CAT: dict[str, int] = {}
OPEN_GOAL = 30    # open 공고 목표 건수 (산업 분석·매칭에 충분)
MAX_TOTAL = 600   # 안전 상한 (과도 수집 방지)

try:
    collector = NarajangterCollector()
    _db = SessionLocal()
    bgn = window.begin.strftime(_FMT)
    end = window.end.strftime(_FMT)

    try:
        open_cnt_now = 0
        for op, cat in OPS:
            if COLLECTED >= MAX_TOTAL:
                break
            cat_cnt = 0
            for page in range(1, 11):  # 최대 10페이지/유형
                if COLLECTED >= MAX_TOTAL:
                    break
                payload = collector.client.get(op, {
                    "inqryDiv": 1,
                    "inqryBgnDt": bgn,
                    "inqryEndDt": end,
                    "pageNo": page,
                    "numOfRows": 100,
                })
                items = collector.client.items(payload)
                if not items:
                    break
                for raw in items:
                    raw["_category"] = cat
                    dto = collector.parse_item(raw)
                    collector._upsert(_db, dto)
                    COLLECTED += 1
                    cat_cnt += 1
                    if dto.status == "open":
                        open_cnt_now += 1

                print(f"    [{cat}] page={page}: {len(items)}건 upsert, "
                      f"open 누적={open_cnt_now}건, total={COLLECTED}건")

                if open_cnt_now >= OPEN_GOAL and cat in ("용역",):
                    break
                if len(items) < 100:
                    break

            COLLECT_BY_CAT[cat] = cat_cnt
            # 용역에서 open 목표 달성이면 나머지 유형 1페이지만 추가
            if open_cnt_now >= OPEN_GOAL and cat == "용역":
                print(f"  용역 open {open_cnt_now}건 >= 목표({OPEN_GOAL}) 달성 → 나머지 유형 1페이지만")
                for op2, cat2 in OPS:
                    if cat2 in COLLECT_BY_CAT or COLLECTED >= MAX_TOTAL:
                        continue
                    payload2 = collector.client.get(op2, {
                        "inqryDiv": 1, "inqryBgnDt": bgn, "inqryEndDt": end,
                        "pageNo": 1, "numOfRows": 100,
                    })
                    items2 = collector.client.items(payload2)
                    if items2:
                        cat2_cnt = 0
                        for raw2 in items2:
                            raw2["_category"] = cat2
                            dto2 = collector.parse_item(raw2)
                            collector._upsert(_db, dto2)
                            COLLECTED += 1
                            cat2_cnt += 1
                        COLLECT_BY_CAT[cat2] = cat2_cnt
                        print(f"    [{cat2}] 1페이지: {cat2_cnt}건 upsert")
                break

        print(f"  OK: 수집 처리 건수 = {COLLECTED} (카테고리별: {COLLECT_BY_CAT})")
    finally:
        _db.close()
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: 수집 실패: {exc}")
    traceback.print_exc()

_db = SessionLocal()
OPEN_OPPS = 0
ALL_TITLES: list[str] = []
try:
    total_db = _db.scalar(sa.text("SELECT COUNT(*) FROM opportunities WHERE source='narajangter'"))
    OPEN_OPPS = _db.scalar(sa.text(
        "SELECT COUNT(*) FROM opportunities WHERE source='narajangter' AND status='open'"
    ))
    print(f"  DB 공고: total={total_db}, open={OPEN_OPPS}")

    # open 공고 타이틀만 수집 (산업 분석 = 실제 매칭 대상 공고 기반)
    title_rows = _db.execute(sa.text(
        "SELECT title, agency, category, status FROM opportunities "
        "WHERE source='narajangter' AND status='open'"
    )).fetchall()
    ALL_TITLES = [r.title for r in title_rows if r.title]
    print(f"  open 공고 타이틀 수 (산업 선택 기반): {len(ALL_TITLES)}")

    # 샘플 3건 출력
    sample = _db.execute(sa.text(
        "SELECT title, agency, category, budget_amount, status FROM "
        "opportunities WHERE source='narajangter' ORDER BY created_at DESC LIMIT 3"
    )).fetchall()
    for i, s in enumerate(sample, 1):
        b = f"{s.budget_amount:,}" if s.budget_amount else "null"
        print(f"    [{i}] {s.title[:50]} | {s.agency} | {s.category} | 예산={b} | {s.status}")
finally:
    _db.close()

if OPEN_OPPS == 0:
    print("\n  WARN: open 공고 0건. 윈도우를 14일로 확장해 재시도...")
    COLLECT_DAYS = 14
    window2 = _Window(begin=now_utc - timedelta(days=COLLECT_DAYS), end=now_utc)
    try:
        collector2 = NarajangterCollector()
        _db = SessionLocal()
        try:
            for page_items in collector2.iter_pages(window2):
                if not page_items:
                    continue
                cat = page_items[0].get("_category", "")
                if cat not in TARGET_CATS:
                    continue
                for raw in page_items[:100]:
                    dto = collector2.parse_item(raw)
                    collector2._upsert(_db, dto)
                    COLLECTED += 1
                break  # 1유형 1페이지 추가
        finally:
            _db.close()
    except Exception as exc2:  # noqa: BLE001
        print(f"  재시도 수집 실패: {exc2}")

    _db = SessionLocal()
    try:
        OPEN_OPPS = _db.scalar(sa.text(
            "SELECT COUNT(*) FROM opportunities WHERE source='narajangter' AND status='open'"
        ))
        title_rows2 = _db.execute(sa.text(
            "SELECT title FROM opportunities WHERE source='narajangter' AND status='open'"
        )).fetchall()
        ALL_TITLES = [r.title for r in title_rows2 if r.title]
        print(f"  재시도 후: open={OPEN_OPPS}, open titles={len(ALL_TITLES)}")
    finally:
        _db.close()

REPORT: dict = {}
REPORT["collect"] = {
    "processed": COLLECTED, "open_opps": OPEN_OPPS,
    "by_category": COLLECT_BY_CAT, "window_days": COLLECT_DAYS,
    "total_titles": len(ALL_TITLES),
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: 데이터-적응 산업 선택
# 수집된 공고 타이틀을 INDUSTRY_KEYWORDS 로 분석 → 가장 매칭 많은 산업 선택
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 2] 데이터-적응 산업 선택 (공고 타이틀 기반)")
from app.services.keywords import INDUSTRY_KEYWORDS, STOPWORDS  # noqa: E402

# 산업별 타이틀 매칭 집계 (STOPWORDS 제외 키워드만 사용)
industry_match_count: dict[str, int] = {}
industry_match_examples: dict[str, list[str]] = {}

for industry, kws in INDUSTRY_KEYWORDS.items():
    # 변별 키워드만 (STOPWORDS 제외)
    discriminative_kws = [kw for kw in kws if kw not in STOPWORDS]
    if not discriminative_kws:
        industry_match_count[industry] = 0
        industry_match_examples[industry] = []
        continue

    matched_titles: list[str] = []
    for title in ALL_TITLES:
        title_lower = title.lower()
        if any(kw.lower() in title_lower for kw in discriminative_kws):
            matched_titles.append(title)

    industry_match_count[industry] = len(matched_titles)
    industry_match_examples[industry] = matched_titles[:3]  # 예시 3개

# 산업별 매칭 결과 표 출력
print("\n  후보 산업별 타이틀 매칭 공고 수:")
sorted_industries = sorted(industry_match_count.items(), key=lambda x: x[1], reverse=True)
for ind, cnt in sorted_industries:
    kws_display = [kw for kw in INDUSTRY_KEYWORDS[ind] if kw not in STOPWORDS]
    print(f"    {ind:12s}: {cnt:3d}건  변별키워드={kws_display}")

# 가장 많이 매칭된 산업 선택 (동률 시 첫 번째)
SELECTED_INDUSTRY = sorted_industries[0][0] if sorted_industries else "IT"
SELECTED_COUNT = sorted_industries[0][1] if sorted_industries else 0
SELECTED_EXAMPLES = industry_match_examples.get(SELECTED_INDUSTRY, [])

# 매칭 0이면 IT로 폴백 (가장 범용)
if SELECTED_COUNT == 0:
    print("\n  WARN: 모든 산업 매칭 0 → IT 폴백 (범용 키워드 사용)")
    SELECTED_INDUSTRY = "IT"
    SELECTED_EXAMPLES = ALL_TITLES[:3]

print(f"\n  선택 산업: [{SELECTED_INDUSTRY}] (매칭 공고 {SELECTED_COUNT}건)")
print("  매칭 예시 타이틀:")
for ex in SELECTED_EXAMPLES:
    print(f"    - {ex[:70]}")

REPORT["industry_selection"] = {
    "selected": SELECTED_INDUSTRY,
    "match_count": SELECTED_COUNT,
    "examples": SELECTED_EXAMPLES,
    "all_counts": dict(sorted_industries),
}

# 선택 산업 기반 회사명/설명 구성 (키워드 파생 돕도록)
INDUSTRY_PROFILES = {
    "IT": {
        "company_name": "(주)테크솔루션",
        "description": "소프트웨어 시스템 정보화 플랫폼 전문 기업. 정보시스템 구축·운영 및 SI 사업 수행.",
    },
    "소프트웨어": {
        "company_name": "(주)소프트라인",
        "description": "소프트웨어 개발 및 정보화 시스템 구축 전문. 플랫폼·솔루션 개발 및 IT 사업 수행.",
    },
    "정보통신": {
        "company_name": "(주)ICT솔루션",
        "description": "정보통신 ICT 네트워크 시스템 전문. 정보통신 인프라 구축·운영 사업 수행.",
    },
    "건설": {
        "company_name": "(주)건설엔지니어링",
        "description": "건설 시공 설계 엔지니어링 전문 기업. 인프라 건설 및 시설 설계·감리 사업 수행.",
    },
    "환경": {
        "company_name": "(주)환경기술연구",
        "description": "환경 생태 수질 대기 관련 조사·분석·연구 전문. 환경영향평가 및 환경개선 사업 수행.",
    },
    "AI": {
        "company_name": "(주)AI데이터솔루션",
        "description": "AI 인공지능 머신러닝 딥러닝 데이터분석 전문. AI 기반 솔루션 개발 및 지능화 사업 수행.",
    },
    "의료": {
        "company_name": "(주)헬스케어솔루션",
        "description": "의료 헬스케어 병원 정보시스템 전문. 의료 IT 플랫폼 구축 및 진단 시스템 사업 수행.",
    },
    "교육": {
        "company_name": "(주)이러닝솔루션",
        "description": "교육 이러닝 콘텐츠 학습 연수 전문. 교육훈련 시스템 개발 및 이러닝 플랫폼 구축.",
    },
    "공간정보": {
        "company_name": "(주)지오스페이스랩",
        "description": "GIS 공간정보 측량 디지털트윈 지리정보 전문. 공간정보 시스템 구축 및 정보화 사업 수행.",
    },
    "GIS": {
        "company_name": "(주)지오스페이스랩",
        "description": "GIS 공간정보 측량 디지털트윈 지리정보 전문. 공간정보 시스템 구축 및 정보화 사업 수행.",
    },
}

profile_info = INDUSTRY_PROFILES.get(SELECTED_INDUSTRY, {
    "company_name": f"(주){SELECTED_INDUSTRY}전문기업",
    "description": f"{SELECTED_INDUSTRY} 분야 전문 기업. 해당 분야 사업 수행.",
})
COMPANY_NAME = profile_info["company_name"]
COMPANY_DESCRIPTION = profile_info["description"]
print(f"  회사명: {COMPANY_NAME}")
print(f"  설명: {COMPANY_DESCRIPTION}")

# ─────────────────────────────────────────────────────────────────────────────
# TestClient 준비
# ─────────────────────────────────────────────────────────────────────────────
from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=True)
API = settings.api_v1_prefix

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: 회원가입 (API)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 3] 회원가입 POST /auth/register (API)")
r = client.post(f"{API}/auth/register", json={
    "email": TEST_EMAIL, "password": TEST_PASSWORD, "company_name": COMPANY_NAME,
})
print(f"  status={r.status_code}")
if r.status_code != 201:
    print(f"  ERROR: {r.text[:300]}")
    sys.exit(1)
tokens = r.json()
ACCESS = tokens["access_token"]
print(f"  OK: access_token 획득(len={len(ACCESS)}), token_type={tokens.get('token_type')}")
H = {"Authorization": f"Bearer {ACCESS}"}
REPORT["register"] = {"status": r.status_code, "has_token": bool(ACCESS)}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: 프로필 입력 (API) — 선택 산업으로
# ─────────────────────────────────────────────────────────────────────────────
banner(f"[STEP 4] 프로필 PUT /company/profile (API) - industry={SELECTED_INDUSTRY}")
profile_body = {
    "industry": SELECTED_INDUSTRY,
    "region": "전국",
    "description": COMPANY_DESCRIPTION,
    "phone": "02-1234-5678",
}
r = client.put(f"{API}/company/profile", headers=H, json=profile_body)
print(f"  PUT status={r.status_code}")
if r.status_code != 200:
    print(f"  ERROR: {r.text[:300]}")
    sys.exit(1)
prof = r.json()
print(f"  OK: industry={prof.get('industry')}, region={prof.get('region')}")
print(f"      onboarding_status={prof.get('onboarding_status')}  (기대: document)")

r2 = client.get(f"{API}/company/profile", headers=H)
prof_get = r2.json()
print(f"  GET 반영확인: industry={prof_get.get('industry')}, status={prof_get.get('onboarding_status')}")
REPORT["profile"] = {
    "put_status": r.status_code,
    "onboarding_status_after_put": prof.get("onboarding_status"),
    "industry": prof_get.get("industry"),
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Company Brain (API) — context 생성 + status 'ready'
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 5] Company Brain POST /company/brain (API)")
r = client.post(f"{API}/company/brain", headers=H)
print(f"  status={r.status_code}")
if r.status_code != 200:
    print(f"  ERROR: {r.text[:300]}")
    sys.exit(1)
brain = r.json()
CC_ID = brain["company_context_id"]
print(f"  OK: company_context_id={CC_ID}")
print(f"      onboarding_status={brain.get('onboarding_status')}  (기대: ready)")

# context_json 확인
_db = SessionLocal()
ctx_json: dict = {}
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
    "industry": ctx_json.get("industry"),
}

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: 회사 임베딩 (동기 보강)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 6] 회사 임베딩 embed_company_context (동기 보강, 실 e5)")
from app.services.embedding.tasks import embed_company_context  # noqa: E402

try:
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
# STEP 7: 공고 임베딩 (동기) — open 공고 전체
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 7] 공고 임베딩 embed_opportunity (동기, 실 e5)")
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
        embed_opportunity.run(str(oid))
        EMBEDDED += 1
    print(f"  OK: 공고 임베딩 = {EMBEDDED}건")
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: 공고 임베딩 실패: {exc}")
    traceback.print_exc()
REPORT["opp_embedding"] = {"embedded": EMBEDDED, "target": len(open_ids)}

if EMBEDDED == 0:
    print("  WARN: 임베딩 공고 0건 → 매칭 불가. 이유: open 공고 없거나 임베딩 실패.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: 매칭 (동기) — run_daily(_llm_fn=None) 직접 호출
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 8] 매칭 run_daily(_llm_fn=None) (동기, 규칙, LLM off)")
from app.services.matching.tasks import run_daily  # noqa: E402

# run_daily 는 settings.match_threshold 를 참조하므로 로컬 settings 패치
import app.core.config as _cfg  # noqa: E402
_original_settings = _cfg.settings
_cfg.settings = settings  # MATCH_THRESHOLD=35인 fresh instance 주입

import app.services.matching.tasks as _match_tasks  # noqa: E402
import app.services.matching.engine as _match_engine  # noqa: E402
_match_tasks.settings = settings
_match_engine.settings = settings

try:
    match_result = run_daily(_llm_fn=None)
    print(f"  OK: {match_result}  (threshold={settings.match_threshold})")
    REPORT["matching"] = match_result
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: run_daily 실패: {exc}")
    traceback.print_exc()
    REPORT["matching"] = {"error": str(exc)}

# ── 후보 규칙 점수 진단 (threshold 필터 전, 전체 분포 확인) ──────────────────
print("\n  ── 후보 규칙 점수 진단 (threshold 필터 전, Top 15 by score) ─────")
from app.services.matching.engine import (  # noqa: E402
    _compute_rule_presets, retrieve_candidates, score_match,
)

CAND_DIAG: list[dict] = []
_db = SessionLocal()
try:
    cand_ids = retrieve_candidates(_db, CC_ID)
    print(f"  retrieve_candidates 결과: {len(cand_ids)}건")
    if cand_ids:
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
            od = {
                "id": str(o.id), "title": o.title or "", "agency": o.agency,
                "region": o.region, "category": o.category, "description": o.description,
            }
            res = score_match(ctx_json, od, _compute_rule_presets(ctx_json, od), llm_complete_json=None)
            CAND_DIAG.append({
                "score": res.score, "subscore": res.subscore,
                "title": o.title, "reasons": res.reasons,
                "agency": o.agency,
            })
        CAND_DIAG.sort(key=lambda x: x["score"], reverse=True)
        print(f"  점수 진단 (상위 {min(15, len(CAND_DIAG))}건):")
        for d in CAND_DIAG[:15]:
            mark = "  <=== >=THRESHOLD" if d["score"] >= settings.match_threshold else ""
            sub = d["subscore"]
            print(f"    score={d['score']:3d}{mark}")
            print(f"        title: {d['title'][:55]}")
            print(f"        agency: {d['agency']}")
            print(f"        sub: tech={sub.get('tech',0)} ind={sub.get('industry',0)} "
                  f"cust={sub.get('customer',0)} reg={sub.get('region',0)} trk={sub.get('track',0)}")
            print(f"        reasons: {d['reasons']}")
    else:
        print("  (후보 없음 — 회사/공고 임베딩 누락 가능)")
finally:
    _db.close()
REPORT["candidate_diagnostic"] = CAND_DIAG[:15]

# ─────────────────────────────────────────────────────────────────────────────
# STEP 9: 추천 조회 + 풀 API 흐름
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 9] 추천 조회 + 풀 API 흐름 (API)")

# 9-1) GET /recommendations/today
r = client.get(f"{API}/recommendations/today", headers=H)
print(f"\n  GET /recommendations/today -> {r.status_code}")
RECS = r.json() if r.status_code == 200 else []
print(f"  추천 건수 = {len(RECS)}")
REPORT["recommendations"] = {"status": r.status_code, "count": len(RECS), "items": RECS}

if RECS:
    print("\n  ── 추천 Top 결과 (실제) ─────────────────────────────────────────")
    for i, it in enumerate(RECS, 1):
        b = f"{it['budget_amount']:,}원" if it.get("budget_amount") else "null(미제공)"
        dd = it.get("d_day")
        dd_s = f"D{dd:+d}" if dd is not None else "D-day 미상"
        sub_info = ""
        # recommendations API 응답에 subscore 없으면 matches 에서 별도 조회
        print(f"  [{i}] {it['title'][:60]}")
        print(f"      기관: {it.get('agency') or 'null'} | 분류: {it.get('category') or 'null'}")
        print(f"      예산: {b} | 마감: {str(it.get('deadline'))[:16] if it.get('deadline') else 'null'} ({dd_s})")
        print(f"      score: {it.get('score')} | reasons: {it.get('reasons')}")
        print(f"      detail_url: {(it.get('detail_url') or 'null')[:80]}")
else:
    print("\n  [주의] 추천 0건 — 아래 진단 확인")
    print(f"    matched (run_daily): {REPORT['matching']}")
    print(f"    후보 진단 점수 분포: {[d['score'] for d in CAND_DIAG[:10]]}")

# subscore 상세 (matches 테이블에서 직접 조회)
_db = SessionLocal()
try:
    match_rows = _db.execute(sa.text(
        "SELECT m.score, m.reason, m.subscore, m.risk, o.title, o.agency, o.budget_amount, "
        "o.deadline, o.detail_url, o.id as opp_id "
        "FROM matches m JOIN opportunities o ON m.opportunity_id = o.id "
        "JOIN companies c ON m.company_id = c.id "
        "JOIN users u ON u.company_id = c.id "
        "WHERE u.email = :email "
        "ORDER BY m.score DESC LIMIT 5"
    ), {"email": TEST_EMAIL}).fetchall()
    if match_rows:
        print(f"\n  ── matches 테이블 상세 ({len(match_rows)}건) ──────────────────")
        for i, row in enumerate(match_rows, 1):
            b = f"{row.budget_amount:,}원" if row.budget_amount else "null"
            dd_raw = row.deadline
            print(f"  [{i}] {row.title[:60]}")
            print(f"      기관: {row.agency}")
            print(f"      예산: {b} | 마감: {str(dd_raw)[:16] if dd_raw else 'null'}")
            print(f"      score: {row.score} | subscore: {row.subscore}")
            print(f"      reason: {row.reason}")
            print(f"      risk: {row.risk}")
            print(f"      detail_url: {(row.detail_url or 'null')[:80]}")
    else:
        print("\n  (matches 테이블 0건)")
finally:
    _db.close()

# 9-2) GET /opportunities
r = client.get(f"{API}/opportunities", headers=H, params={"page": 1, "size": 20})
opp_total = r.json().get("total") if r.status_code == 200 else "?"
print(f"\n  GET /opportunities -> {r.status_code}, total={opp_total}")
REPORT["opportunities_list"] = {"status": r.status_code, "total": opp_total}

# 9-3) POST /opportunities/{id}/actions {type: saved}
SAVED_ID = None
if RECS:
    SAVED_ID = RECS[0]["opportunity_id"]
if not SAVED_ID:
    _db = SessionLocal()
    try:
        row_id = _db.scalar(
            select(Opportunity.id).where(
                Opportunity.source == "narajangter",
                Opportunity.status == "open",
            ).limit(1)
        )
        SAVED_ID = str(row_id) if row_id else None
    finally:
        _db.close()

if SAVED_ID:
    ra = client.post(f"{API}/opportunities/{SAVED_ID}/actions", headers=H, json={"type": "saved"})
    ra2 = client.post(f"{API}/opportunities/{SAVED_ID}/actions", headers=H, json={"type": "saved"})
    ro = client.post(f"{API}/opportunities/{SAVED_ID}/actions", headers=H, json={"type": "opened"})
    print(f"\n  POST actions saved  -> {ra.status_code} | 멱등재호출 -> {ra2.status_code}")
    print(f"  POST actions opened -> {ro.status_code}")
    REPORT["actions"] = {
        "saved": ra.status_code, "saved_idempotent": ra2.status_code,
        "opened": ro.status_code, "target_id": SAVED_ID,
    }
else:
    print("\n  (공고 없음 → actions 스킵)")
    REPORT["actions"] = {"skipped": True}

# 9-4) GET /dashboard/stats
r = client.get(f"{API}/dashboard/stats", headers=H)
stats_data = r.json() if r.status_code == 200 else {"error": r.status_code}
print(f"\n  GET /dashboard/stats -> {r.status_code}: {stats_data}")
REPORT["stats"] = stats_data

# 9-5) 인증 가드
r_noauth = client.get(f"{API}/recommendations/today")
print(f"\n  [인증가드] 토큰 없음 -> {r_noauth.status_code} (기대 401/403)")

# 9-6) 테넌트 격리
r2 = client.post(f"{API}/auth/register", json={
    "email": "other_v2@bizradar-e2e.co.kr", "password": "OtherPass789!",
    "company_name": "(주)타사검증V2",
})
isolation_ok = None
if r2.status_code == 201:
    H2 = {"Authorization": f"Bearer {r2.json()['access_token']}"}
    s2 = client.get(f"{API}/dashboard/stats", headers=H2).json()
    isolation_ok = (s2.get("saved", -1) == 0 and s2.get("opened", -1) == 0)
    print(f"  [테넌트격리] 타사 stats={s2} → 타사에 saved/opened 미노출: {isolation_ok}")
    # 타사 정리
    _db = SessionLocal()
    try:
        ou = _db.scalar(select(User).where(User.email == "other_v2@bizradar-e2e.co.kr"))
        if ou:
            ocid = ou.company_id
            _db.execute(sa.delete(RefreshToken).where(RefreshToken.user_id == ou.id))
            _db.delete(ou)
            _db.commit()
            oc = _db.get(Company, ocid)
            if oc:
                _db.delete(oc)
                _db.commit()
    finally:
        _db.close()
REPORT["auth_guard"] = {"no_token_status": r_noauth.status_code, "tenant_isolation_ok": isolation_ok}

# ─────────────────────────────────────────────────────────────────────────────
# 최종 요약 보고
# ─────────────────────────────────────────────────────────────────────────────
banner("E2E v2 최종 요약 보고")
print(f"""
[1] 수집 결과
  총 처리: {REPORT['collect']['processed']}건
  open 건수: {REPORT['collect']['open_opps']}건
  수집 유형·윈도우: {REPORT['collect']['by_category']} / 최근 {REPORT['collect']['window_days']}일
  총 타이틀 수: {REPORT['collect']['total_titles']}건

[2] 산업 선택 근거
  선택 산업: [{REPORT['industry_selection']['selected']}] (매칭 공고 {REPORT['industry_selection']['match_count']}건)
  산업별 매칭 수 표:""")
for ind, cnt in sorted(REPORT["industry_selection"]["all_counts"].items(), key=lambda x: x[1], reverse=True):
    bar = "#" * min(cnt, 30)
    print(f"    {ind:12s}: {cnt:3d}건  {bar}")
print(f"  선택 산업 예시 타이틀:")
for ex in REPORT["industry_selection"]["examples"]:
    print(f"    - {ex[:70]}")

print(f"""
[3] 각 단계 결과
  회원가입:       status={REPORT['register']['status']}, token={REPORT['register']['has_token']}
  프로필:         PUT={REPORT['profile']['put_status']} status전이={REPORT['profile']['onboarding_status_after_put']} industry={REPORT['profile']['industry']}
  brain:          status={REPORT['brain']['status']} cc_id={REPORT['brain']['cc_id'][:12]}... onboarding={REPORT['brain']['onboarding_status']}
                  keywords={REPORT['brain']['keywords']}
  회사 임베딩:    ok={REPORT['company_embedding'].get('ok')} dim={REPORT['company_embedding'].get('dim')}
  공고 임베딩:    대상={REPORT['opp_embedding']['target']}건 / 완료={REPORT['opp_embedding']['embedded']}건
  매칭:           {REPORT['matching']} (threshold={settings.match_threshold})
  추천:           count={REPORT['recommendations']['count']} ← 핵심 지표
  actions:        {REPORT['actions']}
  stats:          {REPORT['stats']}
  인증가드(무토큰): {REPORT['auth_guard']['no_token_status']} / 테넌트격리={REPORT['auth_guard']['tenant_isolation_ok']}
""")

print("[4] 추천 Top 결과 (실제, 가장 중요)")
if RECS:
    for i, it in enumerate(RECS, 1):
        b = f"{it['budget_amount']:,}원" if it.get("budget_amount") else "null(미제공)"
        dd = it.get("d_day")
        dd_s = f"D{dd:+d}" if dd is not None else "D-day 미상"
        print(f"  [{i}] 제목: {it['title']}")
        print(f"      기관: {it.get('agency') or 'null'} | 예산: {b} | {dd_s}")
        print(f"      score: {it.get('score')} | reasons: {it.get('reasons')}")
        print(f"      detail_url: {(it.get('detail_url') or 'null')[:80]}")
else:
    print("  추천 0건 (정직 보고)")
    if CAND_DIAG:
        scores = [d["score"] for d in CAND_DIAG]
        print(f"  후보 점수 분포: {scores}")
        print(f"  최고 점수: {max(scores) if scores else 0} / threshold={settings.match_threshold}")
        above = sum(1 for s in scores if s >= settings.match_threshold)
        print(f"  threshold 이상: {above}건")
    print(f"  matched (run_daily): {REPORT['matching']}")

print("\n[5] API 흐름")
print(f"  인증: register OK={REPORT['register']['status']==201}")
print(f"  actions: {REPORT['actions']}")
print(f"  stats: {REPORT['stats']}")

print("\n[6] 이슈/관찰")
if REPORT["recommendations"]["count"] == 0:
    print("  - 추천 0건. 원인 분석:")
    m = REPORT["matching"]
    if isinstance(m, dict) and m.get("processed", 0) == 0:
        print("    * processed=0: onboarding_status='ready' 기업 없음 또는 company_context 임베딩 누락")
    if isinstance(m, dict) and m.get("matched", 0) == 0 and m.get("processed", 0) > 0:
        print(f"    * processed={m.get('processed')}: 기업 처리됨, matched=0")
        print(f"    * skipped={m.get('skipped')}: threshold({settings.match_threshold}) 미달")
        if CAND_DIAG:
            scores = [d["score"] for d in CAND_DIAG]
            print(f"    * 후보 최고점수={max(scores) if scores else 0}, "
                  f"가장 많이 매칭된 산업={REPORT['industry_selection']['selected']}({REPORT['industry_selection']['match_count']}건)")
        print("    * 수집 도메인 다양성 부족 가능성 또는 임베딩 유사도 낮음")
else:
    print(f"  - 추천 {REPORT['recommendations']['count']}건 확인. 정상 매칭.")
    if RECS:
        scores_rec = [it.get("score") for it in RECS]
        print(f"  - score 분포: {scores_rec}")
        nb = sum(1 for it in RECS if not it.get("budget_amount"))
        nd = sum(1 for it in RECS if not it.get("deadline"))
        nu = sum(1 for it in RECS if not it.get("detail_url"))
        print(f"  - 빈 필드: budget={nb}/{len(RECS)} deadline={nd}/{len(RECS)} detail_url={nu}/{len(RECS)}")

banner("E2E v2 검증 완료 — 정리 단계 없음(docker는 호출자가 정리)")
print("  스크립트: scripts/onboarding_e2e_match.py (보존)")
print("  정리: docker compose -f docker-compose.dev.yml down -v (검증 후 직접 실행 권장)")
