# -*- coding: utf-8 -*-
"""라이브 브라우저 데모용 시드 스크립트.

데모 계정(demo@bizradar.ai / Demo1234!) + 실 나라장터 공고 수집 + 매칭 데이터를
실 PG(5433)에 영속 저장. TestClient/teardown 없음. 재실행 안전(upsert/재생성).

실행 (backend/ 에서):
    PYTHONPATH=. python scripts/seed_demo.py

전제:
- docker compose -f docker-compose.dev.yml up -d --wait postgres  (host 5433)
- alembic upgrade head 완료
- .env: NARAJANGTER_SERVICE_KEY=<실키>
- fastembed e5-large 모델 캐시 (또는 온라인 다운로드 가능)
"""
from __future__ import annotations

import io
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Windows cp949 콘솔 인코딩 오류 방지
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ("utf-8", "utf8"):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# backend/ 를 sys.path / cwd 로 설정
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))
os.chdir(BACKEND_DIR)

# MATCH_THRESHOLD 35 강제 (E2E처럼 — .env의 45를 데모 시드 목적으로 override)
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


banner("BizRadar AI -- 데모 시드 스크립트 (라이브 브라우저 데모용)")

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

from app.core.config import Settings  # noqa: E402
settings = Settings()  # MATCH_THRESHOLD=35 반영한 fresh instance

print(f"  DATABASE_URL:      {settings.database_url}")
print(f"  EMBEDDING_PROVIDER:{settings.embedding_provider}")
print(f"  EMBEDDING_MODEL:   {settings.embedding_model}")
print(f"  EMBEDDING_DIM:     {settings.embedding_dim}")
print(f"  MATCH_THRESHOLD:   {settings.match_threshold}")
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
# 데모 계정 상수
# ─────────────────────────────────────────────────────────────────────────────
DEMO_EMAIL = "demo@bizradar.ai"
DEMO_PASSWORD = "Demo1234!"

# ─────────────────────────────────────────────────────────────────────────────
# 사전 정리: 재실행 안전 (기존 데모 계정 관련 데이터 정리 후 재생성)
# ─────────────────────────────────────────────────────────────────────────────
from app.db.models.accounts import Company, NotificationSetting, RefreshToken, User  # noqa: E402
from app.db.models.company_context import CompanyContext  # noqa: E402
from app.db.models.opportunity import Match, Opportunity, UserOpportunityAction  # noqa: E402

print("\n  사전 정리(재실행 안전)...")
_db = SessionLocal()
try:
    u = _db.scalar(select(User).where(User.email == DEMO_EMAIL))
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
        print("  OK: 기존 데모 계정 데이터 삭제 완료")
    else:
        print("  (정리 대상 없음 — 첫 실행)")

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
# STEP 1: 실 수집 — open 공고 30건 이상 확보 목표 (용역 다페이지, 최대 600건)
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
    from app.db.models.opportunity import Source as Src  # noqa: PLC0415, F811
    if _db.get(Src, "narajangter") is None:
        _db.add(Src(code="narajangter", name="나라장터(조달청) 입찰공고",
                    tier=0, collector="narajangter", enabled=True))
        _db.commit()
finally:
    _db.close()

COLLECTED = 0
COLLECT_BY_CAT: dict[str, int] = {}
OPEN_GOAL = 30
MAX_TOTAL = 600

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

    title_rows = _db.execute(sa.text(
        "SELECT title FROM opportunities WHERE source='narajangter' AND status='open'"
    )).fetchall()
    ALL_TITLES = [r.title for r in title_rows if r.title]
    print(f"  open 공고 타이틀 수 (산업 선택 기반): {len(ALL_TITLES)}")

    sample = _db.execute(sa.text(
        "SELECT title, agency, category, budget_amount, status FROM "
        "opportunities WHERE source='narajangter' ORDER BY created_at DESC LIMIT 3"
    )).fetchall()
    for i, s in enumerate(sample, 1):
        b = f"{s.budget_amount:,}" if s.budget_amount else "null"
        print(f"    [{i}] {s.title[:50]} | {s.agency} | {s.category} | 예산={b} | {s.status}")
finally:
    _db.close()

# open 공고가 없으면 수집 윈도우 확장 재시도
if OPEN_OPPS == 0:
    print("\n  WARN: open 공고 0건. 윈도우를 30일로 확장해 재시도...")
    COLLECT_DAYS = 30
    window2 = _Window(begin=now_utc - timedelta(days=COLLECT_DAYS), end=now_utc)
    try:
        collector2 = NarajangterCollector()
        _db = SessionLocal()
        bgn2 = window2.begin.strftime(_FMT)
        end2 = window2.end.strftime(_FMT)
        try:
            for op2, cat2 in OPS[:2]:  # 물품+용역만
                payload2 = collector2.client.get(op2, {
                    "inqryDiv": 1, "inqryBgnDt": bgn2, "inqryEndDt": end2,
                    "pageNo": 1, "numOfRows": 100,
                })
                items2 = collector2.client.items(payload2)
                if items2:
                    for raw2 in items2:
                        raw2["_category"] = cat2
                        dto2 = collector2.parse_item(raw2)
                        collector2._upsert(_db, dto2)
                        COLLECTED += 1
                    print(f"    [{cat2}] 재시도 1페이지: {len(items2)}건 upsert")
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

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: 데이터-적응 산업 선택
# open 공고 타이틀을 INDUSTRY_KEYWORDS로 분석 → 최다 매칭 산업 선택
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 2] 데이터-적응 산업 선택 (open 공고 타이틀 기반)")
from app.services.keywords import INDUSTRY_KEYWORDS, STOPWORDS  # noqa: E402

industry_match_count: dict[str, int] = {}
industry_match_examples: dict[str, list[str]] = {}

for industry, kws in INDUSTRY_KEYWORDS.items():
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
    industry_match_examples[industry] = matched_titles[:3]

print("\n  후보 산업별 타이틀 매칭 공고 수:")
sorted_industries = sorted(industry_match_count.items(), key=lambda x: x[1], reverse=True)
for ind, cnt in sorted_industries:
    kws_display = [kw for kw in INDUSTRY_KEYWORDS[ind] if kw not in STOPWORDS]
    print(f"    {ind:12s}: {cnt:3d}건  변별키워드={kws_display}")

SELECTED_INDUSTRY = sorted_industries[0][0] if sorted_industries else "IT"
SELECTED_COUNT = sorted_industries[0][1] if sorted_industries else 0
SELECTED_EXAMPLES = industry_match_examples.get(SELECTED_INDUSTRY, [])

if SELECTED_COUNT == 0:
    print("\n  WARN: 모든 산업 매칭 0 → IT 폴백 (범용 키워드 사용)")
    SELECTED_INDUSTRY = "IT"
    SELECTED_EXAMPLES = ALL_TITLES[:3]

print(f"\n  선택 산업: [{SELECTED_INDUSTRY}] (매칭 공고 {SELECTED_COUNT}건)")
print("  매칭 예시 타이틀:")
for ex in SELECTED_EXAMPLES:
    print(f"    - {ex[:70]}")

# 선택 산업 기반 회사명/설명 구성
INDUSTRY_PROFILES = {
    "IT": {
        "company_name": "데모테크(주)",
        "description": "소프트웨어 시스템 정보화 플랫폼 전문 기업. 정보시스템 구축·운영 및 SI 사업 수행.",
    },
    "소프트웨어": {
        "company_name": "데모소프트(주)",
        "description": "소프트웨어 개발 및 정보화 시스템 구축 전문. 플랫폼·솔루션 개발 및 IT 사업 수행.",
    },
    "정보통신": {
        "company_name": "데모ICT(주)",
        "description": "정보통신 ICT 네트워크 시스템 전문. 정보통신 인프라 구축·운영 사업 수행.",
    },
    "건설": {
        "company_name": "데모건설엔지니어링(주)",
        "description": "건설 시공 설계 엔지니어링 전문 기업. 인프라 건설 및 시설 설계·감리 사업 수행.",
    },
    "환경": {
        "company_name": "데모환경기술(주)",
        "description": "환경 생태 수질 대기 관련 조사·분석·연구 전문. 환경영향평가 및 환경개선 사업 수행.",
    },
    "AI": {
        "company_name": "데모AI솔루션(주)",
        "description": "AI 인공지능 머신러닝 딥러닝 데이터분석 전문. AI 기반 솔루션 개발 및 지능화 사업 수행.",
    },
    "의료": {
        "company_name": "데모메디칼(주)",
        "description": "의료 헬스케어 병원 정보시스템 전문. 의료 IT 플랫폼 구축 및 진단 시스템 사업 수행.",
    },
    "교육": {
        "company_name": "데모이러닝(주)",
        "description": "교육 이러닝 콘텐츠 학습 연수 전문. 교육훈련 시스템 개발 및 이러닝 플랫폼 구축.",
    },
    "공간정보": {
        "company_name": "데모지오스페이스(주)",
        "description": "GIS 공간정보 측량 디지털트윈 지리정보 전문. 공간정보 시스템 구축 및 정보화 사업 수행.",
    },
    "GIS": {
        "company_name": "데모지오스페이스(주)",
        "description": "GIS 공간정보 측량 디지털트윈 지리정보 전문. 공간정보 시스템 구축 및 정보화 사업 수행.",
    },
}

profile_info = INDUSTRY_PROFILES.get(SELECTED_INDUSTRY, {
    "company_name": f"데모{SELECTED_INDUSTRY}전문(주)",
    "description": f"{SELECTED_INDUSTRY} 분야 전문 기업. 해당 분야 사업 수행.",
})
COMPANY_NAME = profile_info["company_name"]
COMPANY_DESCRIPTION = profile_info["description"]
print(f"  회사명: {COMPANY_NAME}")
print(f"  설명:   {COMPANY_DESCRIPTION}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: 데모 계정 생성 (auth_service.register 와 동일 경로)
# argon2 해시 → UI 로그인 가능
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 3] 데모 계정 생성 (auth_service 경로)")
from app.core.security import hash_password  # noqa: E402

_db = SessionLocal()
try:
    # Company 생성
    demo_company = Company(
        name=COMPANY_NAME,
        industry=SELECTED_INDUSTRY,
        description=COMPANY_DESCRIPTION,
        region="전국",
        phone="02-1234-5678",
        onboarding_status="profile",
    )
    _db.add(demo_company)
    _db.flush()

    # User 생성 (argon2 해시 — UI 로그인 가능)
    demo_user = User(
        email=DEMO_EMAIL,
        password_hash=hash_password(DEMO_PASSWORD),
        company_id=demo_company.id,
        role="company_admin",
    )
    _db.add(demo_user)
    _db.flush()

    # NotificationSetting 생성
    _db.add(NotificationSetting(company_id=demo_company.id))
    _db.flush()

    _db.commit()
    COMPANY_ID = str(demo_company.id)
    print(f"  OK: 데모 계정 생성 완료")
    print(f"  email:      {DEMO_EMAIL}")
    print(f"  password:   {DEMO_PASSWORD}")
    print(f"  company:    {COMPANY_NAME} ({SELECTED_INDUSTRY})")
    print(f"  company_id: {COMPANY_ID}")
finally:
    _db.close()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: company.industry / description / onboarding_status 설정
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 4] Company 프로필 설정 (industry/description/onboarding_status=ready)")
_db = SessionLocal()
try:
    company = _db.get(Company, uuid.UUID(COMPANY_ID))
    company.industry = SELECTED_INDUSTRY
    company.description = COMPANY_DESCRIPTION
    company.onboarding_status = "ready"
    _db.commit()
    print(f"  OK: industry={company.industry}, status={company.onboarding_status}")
finally:
    _db.close()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Company Brain — build_company_context (LLM off, 프로필 기반)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 5] Company Brain (build_company_context, LLM off)")
from app.services.company_brain.service import build_company_context  # noqa: E402

_db = SessionLocal()
try:
    CC_ID = build_company_context(COMPANY_ID, db=_db, llm_complete_json=None)
    _db.commit()
    print(f"  OK: company_context_id={CC_ID}")

    cc = _db.get(CompanyContext, uuid.UUID(CC_ID))
    ctx_json: dict = cc.context_json or {}
    print(f"      context.industry={ctx_json.get('industry')}")
    print(f"      context.regions={ctx_json.get('regions')}")
    print(f"      context.keywords={ctx_json.get('keywords')}")
finally:
    _db.close()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: 회사 임베딩 (동기, 실 e5)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 6] 회사 임베딩 embed_company_context (동기, 실 e5)")
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
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: 회사 임베딩 실패: {exc}")
    traceback.print_exc()
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

if EMBEDDED == 0:
    print("  WARN: 임베딩 공고 0건 → 매칭 불가.")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: 매칭 (동기) — run_daily(_llm_fn=None) 직접 호출
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 8] 매칭 run_daily(_llm_fn=None) (동기, 규칙, LLM off)")
from app.services.matching.tasks import run_daily  # noqa: E402

# settings 패치 (MATCH_THRESHOLD=35 반영)
import app.core.config as _cfg  # noqa: E402
_cfg.settings = settings
import app.services.matching.tasks as _match_tasks  # noqa: E402
import app.services.matching.engine as _match_engine  # noqa: E402
_match_tasks.settings = settings
_match_engine.settings = settings

try:
    match_result = run_daily(_llm_fn=None)
    print(f"  OK: {match_result}  (threshold={settings.match_threshold})")
    MATCHED = match_result.get("matched", 0)
except Exception as exc:  # noqa: BLE001
    import traceback
    print(f"  ERROR: run_daily 실패: {exc}")
    traceback.print_exc()
    MATCHED = 0
    match_result = {"error": str(exc)}

# matched=0 이면 수집 윈도우 넓혀 재시도
if MATCHED == 0:
    print("\n  WARN: matched=0. 수집 윈도우를 30일로 넓혀 공고 추가 수집 후 재매칭...")
    COLLECT_DAYS2 = 30
    window3 = _Window(begin=now_utc - timedelta(days=COLLECT_DAYS2), end=now_utc)
    try:
        collector3 = NarajangterCollector()
        _db = SessionLocal()
        bgn3 = window3.begin.strftime(_FMT)
        end3 = window3.end.strftime(_FMT)
        try:
            added = 0
            for op3, cat3 in OPS:
                payload3 = collector3.client.get(op3, {
                    "inqryDiv": 1, "inqryBgnDt": bgn3, "inqryEndDt": end3,
                    "pageNo": 1, "numOfRows": 100,
                })
                items3 = collector3.client.items(payload3)
                if items3:
                    for raw3 in items3:
                        raw3["_category"] = cat3
                        dto3 = collector3.parse_item(raw3)
                        collector3._upsert(_db, dto3)
                        added += 1
                    print(f"    [{cat3}] 30일 윈도우 재시도: {len(items3)}건 upsert")
            print(f"  재시도 추가 처리: {added}건")
        finally:
            _db.close()
    except Exception as exc3:  # noqa: BLE001
        print(f"  재시도 수집 실패: {exc3}")

    # 새로 수집된 공고 임베딩
    _db = SessionLocal()
    try:
        new_open_ids = _db.scalars(
            select(Opportunity.id).where(
                Opportunity.source == "narajangter",
                Opportunity.status == "open",
                Opportunity.embedding.is_(None),
            )
        ).all()
    finally:
        _db.close()
    print(f"  추가 임베딩 대상: {len(new_open_ids)}건")
    for oid in new_open_ids:
        try:
            embed_opportunity.run(str(oid))
            EMBEDDED += 1
        except Exception:  # noqa: BLE001
            pass

    # 재매칭
    try:
        match_result = run_daily(_llm_fn=None)
        print(f"  재매칭 결과: {match_result}")
        MATCHED = match_result.get("matched", 0)
    except Exception as exc4:  # noqa: BLE001
        print(f"  재매칭 실패: {exc4}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 9: 추천 Top3 조회 (matches 테이블 직접)
# ─────────────────────────────────────────────────────────────────────────────
banner("[STEP 9] 추천 Top3 조회 (matches 테이블)")
TOP3: list[dict] = []
_db = SessionLocal()
try:
    match_rows = _db.execute(sa.text(
        "SELECT m.score, m.reason, m.subscore, o.title, o.agency, o.budget_amount, "
        "o.deadline, o.detail_url "
        "FROM matches m JOIN opportunities o ON m.opportunity_id = o.id "
        "JOIN companies c ON m.company_id = c.id "
        "JOIN users u ON u.company_id = c.id "
        "WHERE u.email = :email "
        "ORDER BY m.score DESC LIMIT 3"
    ), {"email": DEMO_EMAIL}).fetchall()

    for row in match_rows:
        TOP3.append({
            "title": row.title,
            "agency": row.agency,
            "score": row.score,
            "budget_amount": row.budget_amount,
            "deadline": str(row.deadline)[:16] if row.deadline else None,
            "detail_url": row.detail_url,
        })
finally:
    _db.close()

# ─────────────────────────────────────────────────────────────────────────────
# 최종 요약 보고
# ─────────────────────────────────────────────────────────────────────────────
banner("데모 시드 완료 — 최종 보고")
print(f"""
[데모 계정]
  email:    {DEMO_EMAIL}
  password: {DEMO_PASSWORD}
  company:  {COMPANY_NAME}
  industry: {SELECTED_INDUSTRY}

[수집/임베딩/매칭]
  수집 처리: {COLLECTED}건 (윈도우: {COLLECT_DAYS}일)
  open 공고: {OPEN_OPPS}건
  공고 임베딩: {EMBEDDED}건
  매칭 결과: {match_result}
  matched: {MATCHED}건
""")

if TOP3:
    print("[추천 Top3]")
    for i, it in enumerate(TOP3, 1):
        b = f"{it['budget_amount']:,}원" if it.get("budget_amount") else "null(미제공)"
        print(f"  [{i}] {it['title']}")
        print(f"      기관: {it.get('agency') or 'null'} | 예산: {b} | 마감: {it.get('deadline') or 'null'}")
        print(f"      score: {it.get('score')} | url: {(it.get('detail_url') or 'null')[:80]}")
else:
    print("[추천 Top3] 0건 (matched=0)")
    print("  matched=0 원인: open 공고 수 부족 또는 임베딩 유사도 낮음")
    print(f"  run_daily 결과: {match_result}")

print(f"""
[PG 상태]
  PG는 계속 실행 중 — docker compose down 하지 않음.
  DB=bizradar (포트 5433)

[다음 단계 (호출자)]
  uvicorn:  DATABASE_URL=postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar uvicorn app.main:app --port 8000
  frontend: cd frontend && npm run dev  (포트 3000)
  로그인:   email={DEMO_EMAIL} / password={DEMO_PASSWORD}
""")

banner("seed_demo.py 완료")
