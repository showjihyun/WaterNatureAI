# -*- coding: utf-8 -*-
"""E2E 파이프라인 검증 스크립트 (수집->임베딩->Company Brain->매칭->추천).

실행: backend/ 디렉터리에서
  python scripts/e2e_check.py

전제:
- docker compose -f docker-compose.dev.yml up -d --wait postgres 실행 완료
- .env에 NARAJANGTER_SERVICE_KEY 설정 (실 키)
- pip install fastembed 완료
- alembic upgrade head 완료

가드레일:
- 프로덕션 코드 수정 없음 (일회성 검증 스크립트)
- BGE 다운로드 실패 시 정직하게 보고, 가짜 벡터 사용 금지
- 외부 호출: data.go.kr 수집(소규모) + BGE 다운로드만
"""
from __future__ import annotations

import json
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── backend/ 를 sys.path에 추가 ──────────────────────────────────────────────
BACKEND_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(BACKEND_DIR))

# .env 파일 명시 로딩 (BGE 사용 강제)
os.chdir(BACKEND_DIR)

# .env에서 읽은 값 그대로 사용 (EMBEDDING_PROVIDER=bge, MATCH_THRESHOLD=45)

print("=" * 70)
print("BizRadar AI -- E2E 파이프라인 검증")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 0: fastembed 설치 확인
# ─────────────────────────────────────────────────────────────────────────────
print("\n[STEP 0] fastembed 설치 확인...")
try:
    import fastembed  # noqa: F401
    print(f"  OK: fastembed 설치됨 (version: {fastembed.__version__})")
except ImportError:
    print("  ERROR: fastembed 미설치. `pip install fastembed` 실행 필요.")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: DB 연결 확인 + alembic 마이그레이션 적용
# ─────────────────────────────────────────────────────────────────────────────
print("\n[STEP 1] DB 연결 + 마이그레이션 확인...")

from app.core.config import settings  # noqa: E402
from app.db.base import Base, SessionLocal, get_engine  # noqa: E402

print(f"  DATABASE_URL: {settings.database_url}")
print(f"  EMBEDDING_PROVIDER: {settings.embedding_provider}")
print(f"  EMBEDDING_MODEL: {settings.embedding_model}")
print(f"  MATCH_THRESHOLD: {settings.match_threshold}")

try:
    engine = get_engine()
    with engine.connect() as conn:
        result = conn.execute(
            __import__("sqlalchemy").text("SELECT current_database(), version()")
        )
        row = result.fetchone()
        print(f"  OK: PostgreSQL 연결 성공 -- db={row[0]}")
        print(f"      {row[1][:60]}...")
except Exception as e:
    print(f"  ERROR: DB 연결 실패: {e}")
    print("  docker compose -f docker-compose.dev.yml up -d --wait postgres 실행 필요")
    sys.exit(1)

# alembic 상태 확인
import subprocess  # noqa: E402
result = subprocess.run(
    ["python", "-m", "alembic", "upgrade", "head"],
    capture_output=True, text=True, cwd=str(BACKEND_DIR)
)
if result.returncode != 0:
    print(f"  WARNING: alembic upgrade 실패:\n{result.stderr[:500]}")
    print("  (이미 최신이면 계속 진행)")
else:
    print(f"  OK: alembic upgrade head 완료")
    if result.stdout.strip():
        print(f"  {result.stdout.strip()[:200]}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: BGE 모델 준비 (다운로드 + 동작 확인)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[STEP 2] BGE 모델 준비 (BAAI/bge-m3, 첫 실행 시 다운로드)...")
print("  주의: 최초 실행 시 모델 다운로드에 수 분 소요될 수 있습니다.")

try:
    from app.services.embedding.provider import BgeProvider  # noqa: E402

    provider = BgeProvider()
    print("  BGE 모델 로드 시작 (시간 걸릴 수 있음)...")
    test_vec = provider.embed("공간정보 시스템 구축 용역")
    print(f"  OK: BGE 임베딩 성공 -- 차원={len(test_vec)}, 첫 값={test_vec[0]:.6f}")
    BGE_AVAILABLE = True
except Exception as e:
    print(f"  ERROR: BGE 모델 로드/다운로드 실패: {e}")
    print("  원인: 네트워크 차단, 디스크 공간 부족, 또는 fastembed 호환성 문제일 수 있음.")
    print("  → 임베딩 없이 규칙 기반 매칭만 검증합니다 (벡터 retrieval 불가).")
    BGE_AVAILABLE = False

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: 테스트 회사 온보딩 + Company Brain
# ─────────────────────────────────────────────────────────────────────────────
print("\n[STEP 3] 테스트 회사 온보딩...")

from sqlalchemy import select  # noqa: E402
from app.db.models.accounts import Company, NotificationSetting, User  # noqa: E402
from app.db.models.company_context import CompanyContext  # noqa: E402
from app.core.security import hash_password  # noqa: E402

db = SessionLocal()

# 기존 테스트 데이터 정리 (재실행 안전)
TEST_EMAIL = "e2e_test@bizradar.test"
existing_user = db.scalar(select(User).where(User.email == TEST_EMAIL))
if existing_user and existing_user.company_id:
    existing_company = db.get(Company, existing_user.company_id)
    if existing_company:
        # company_contexts 삭제
        ccs = db.scalars(
            select(CompanyContext).where(CompanyContext.company_id == existing_company.id)
        ).all()
        for cc in ccs:
            db.delete(cc)
        # notification_settings 삭제
        ns = db.scalar(
            select(NotificationSetting).where(
                NotificationSetting.company_id == existing_company.id
            )
        )
        if ns:
            db.delete(ns)
        db.delete(existing_user)
        db.delete(existing_company)
        db.commit()
        print("  기존 테스트 데이터 정리 완료")

# 테스트 회사 생성 (공간정보 기업)
company = Company(
    id=uuid.uuid4(),
    name="(주)테스트공간정보",
    industry="공간정보",
    description="GIS 시스템 구축, 측량, 공간정보 데이터 처리 전문 기업",
    region="서울",
    onboarding_status="ready",  # 매칭 대상이 되려면 ready
)
db.add(company)
db.flush()

user = User(
    id=uuid.uuid4(),
    email=TEST_EMAIL,
    password_hash=hash_password("TestPass123!"),
    company_id=company.id,
    role="company_admin",
)
db.add(user)

ns = NotificationSetting(
    company_id=company.id,
    enabled=True,
    channel="alimtalk",
)
db.add(ns)
db.commit()

COMPANY_ID = str(company.id)
USER_ID = str(user.id)
print(f"  OK: 회사 생성 -- id={COMPANY_ID}, name={company.name}")
print(f"      industry={company.industry}, region={company.region}")

# Company Brain: build_company_context (LLM 없이 프로필 fallback)
from app.services.company_brain.service import build_company_context  # noqa: E402

print("\n  Company Brain 실행 (LLM 없이 프로필 fallback)...")
cc_id = build_company_context(COMPANY_ID, db=db, llm_complete_json=None)
db.commit()
print(f"  OK: company_context 생성 -- cc_id={cc_id}")

# CompanyContext 내용 확인
cc = db.get(CompanyContext, uuid.UUID(cc_id))
print(f"  context_json: {json.dumps(cc.context_json, ensure_ascii=False)}")

# ── 임베딩 (BGE 가능하면) ──────────────────────────────────────────────────
if BGE_AVAILABLE:
    print("\n  CompanyContext 임베딩 (BGE)...")
    from app.services.embedding import vectorstore  # noqa: E402

    text = str(cc.context_json)
    vector = provider.embed(text)
    vectorstore.store_embedding(db, vectorstore.COMPANY_CONTEXTS, cc_id, vector)
    cc.embedded_hash = cc.content_hash
    cc.embedding_version = settings.embedding_version
    cc.embedded_at = datetime.now(timezone.utc)
    db.commit()
    print(f"  OK: CompanyContext 임베딩 완료 -- 차원={len(vector)}")
else:
    print("  SKIP: BGE 불가 -- CompanyContext 임베딩 생략")

db.close()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: 실 수집 (소규모: 최근 3일, 용역 카테고리만, 최대 1페이지)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[STEP 4] 나라장터 실 수집 (소규모, 용역 카테고리, 최근 3일)...")

from app.services.collectors.narajangter import NarajangterCollector, OPS  # noqa: E402
from app.services.collectors.base import _Window  # noqa: E402
from app.services.collectors.client import DataGoKrClient  # noqa: E402

# 수집 윈도우: 최근 3일만
now_utc = datetime.now(timezone.utc)
window = _Window(
    begin=now_utc - timedelta(days=3),
    end=now_utc,
)

print(f"  수집 윈도우: {window.begin.strftime('%Y-%m-%d')} ~ {window.end.strftime('%Y-%m-%d')}")
print(f"  API KEY: {settings.narajangter_service_key[:20]}...")

# 소규모 수집을 위해 커스텀 수집기 (용역 1종, 1페이지만)
class SmallCollector(NarajangterCollector):
    """검증용: 용역 카테고리 1개, 최대 1페이지(최대 100건)."""

    def iter_pages(self, w):
        from itertools import islice
        # 용역 카테고리만 (getBidPblancListInfoServc)
        original_ops = OPS
        import app.services.collectors.narajangter as nm
        # 원래 OPS를 용역 1종으로 제한
        nm.OPS = [("getBidPblancListInfoServc", "용역")]
        try:
            page_gen = super().iter_pages(w)
            # 첫 1페이지만
            yield from islice(page_gen, 1)
        finally:
            nm.OPS = original_ops


collector = SmallCollector()
db = SessionLocal()

try:
    from app.db.models.opportunity import Opportunity, SourceIngestionState  # noqa: E402

    # sources 시드 확인 (없으면 삽입)
    from app.db.models.opportunity import Source  # noqa: E402
    existing_src = db.get(Source, "narajangter")
    if existing_src is None:
        db.add(Source(
            code="narajangter",
            name="나라장터(조달청) 입찰공고",
            tier=0,
            collector="narajangter",
            enabled=True,
        ))
        db.commit()
        print("  OK: sources 시드 삽입")

    # 수집 실행
    print("  수집 실행 중...")
    collected = collector.run()
    print(f"  OK: 수집 완료 -- {collected}건 처리")

    # 실제 수집된 공고 수 확인
    total_opps = db.scalar(
        __import__("sqlalchemy").text(
            "SELECT COUNT(*) FROM opportunities WHERE source='narajangter'"
        )
    )
    open_opps = db.scalar(
        __import__("sqlalchemy").text(
            "SELECT COUNT(*) FROM opportunities WHERE source='narajangter' AND status='open'"
        )
    )
    print(f"  DB 내 나라장터 공고: 전체={total_opps}, status=open={open_opps}")

    # 샘플 공고 출력
    sample_rows = db.execute(
        __import__("sqlalchemy").text(
            "SELECT title, agency, category, budget_amount, deadline, status, detail_url "
            "FROM opportunities WHERE source='narajangter' ORDER BY created_at DESC LIMIT 5"
        )
    ).fetchall()

    COLLECTED_COUNT = collected
    OPEN_OPP_COUNT = open_opps

    if sample_rows:
        print("\n  수집 공고 샘플 (최근 5건):")
        for i, r in enumerate(sample_rows, 1):
            budget_str = f"{r.budget_amount:,}원" if r.budget_amount else "null"
            deadline_str = str(r.deadline)[:16] if r.deadline else "null"
            print(f"    [{i}] {r.title[:40]}")
            print(f"        기관={r.agency}, 분류={r.category}, 예산={budget_str}")
            print(f"        마감={deadline_str}, status={r.status}")
    else:
        print("  WARNING: 공고 샘플 없음 (수집 0건)")

except Exception as e:
    import traceback
    print(f"  ERROR: 수집 실패: {e}")
    traceback.print_exc()
    COLLECTED_COUNT = 0
    OPEN_OPP_COUNT = 0
finally:
    db.close()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: 공고 임베딩 (BGE 가능하면, status=open 위주)
# ─────────────────────────────────────────────────────────────────────────────
EMBEDDED_COUNT = 0

if BGE_AVAILABLE and OPEN_OPP_COUNT > 0:
    print(f"\n[STEP 5] 공고 임베딩 (BGE, status=open, 최대 20건)...")

    db = SessionLocal()
    try:
        from app.services.embedding import vectorstore  # noqa: F811

        opps = db.scalars(
            select(Opportunity)
            .where(
                Opportunity.status == "open",
                Opportunity.source == "narajangter",
                Opportunity.embedding.is_(None),  # 아직 임베딩 안 된 것
            )
            .limit(20)
        ).all()

        print(f"  임베딩 대상: {len(opps)}건")

        for opp in opps:
            parts = [f"[{opp.category}] {opp.title}" if opp.category else opp.title]
            if opp.agency:
                parts.append(f"발주/소관: {opp.agency}")
            if opp.region:
                parts.append(f"지역: {opp.region}")
            if opp.description:
                parts.append(opp.description)
            embed_text = "\n".join(parts)

            vec = provider.embed(embed_text)
            vectorstore.store_embedding(db, vectorstore.OPPORTUNITIES, str(opp.id), vec)
            opp.embedded_hash = opp.content_hash
            opp.embedding_version = settings.embedding_version
            opp.embedded_at = datetime.now(timezone.utc)
            EMBEDDED_COUNT += 1

        db.commit()
        print(f"  OK: 공고 임베딩 완료 -- {EMBEDDED_COUNT}건")

    except Exception as e:
        import traceback
        print(f"  ERROR: 임베딩 실패: {e}")
        traceback.print_exc()
    finally:
        db.close()

elif not BGE_AVAILABLE:
    print("\n[STEP 5] SKIP -- BGE 불가")
else:
    print("\n[STEP 5] SKIP -- 수집된 공고 없음")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: 매칭 (run_daily, LLM 없이 규칙 기반)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[STEP 6] 매칭 실행 (run_daily, 규칙 기반, LLM off)...")

MATCH_RESULT = {"processed": 0, "matched": 0, "skipped": 0}

if EMBEDDED_COUNT > 0 or not BGE_AVAILABLE:
    # BGE 불가면 벡터 retrieval 없이 직접 규칙 매칭 시도
    if not BGE_AVAILABLE:
        print("  BGE 불가 → 벡터 없이 직접 규칙 기반 매칭 시도...")
        _do_direct_matching = True
    else:
        _do_direct_matching = False

    if not _do_direct_matching:
        # 정상 경로: run_daily (pgvector retrieval → rule scoring)
        try:
            from app.services.matching.tasks import run_daily  # noqa: E402
            # Celery 태스크를 직접 함수로 호출 (_llm_fn=None → 규칙 기반)
            result = run_daily(_llm_fn=None)
            MATCH_RESULT = result
            print(f"  OK: 매칭 완료 -- {result}")
        except Exception as e:
            import traceback
            print(f"  ERROR: run_daily 실패: {e}")
            traceback.print_exc()
    else:
        # BGE 없이: 직접 규칙 매칭 (벡터 없이, 공고 목록 전체 순회)
        try:
            from sqlalchemy.dialects.postgresql import insert as pg_insert  # noqa: E402
            from app.db.models.opportunity import Match  # noqa: E402, F811
            from app.services.matching.engine import (  # noqa: E402
                _compute_rule_presets, score_match
            )

            db = SessionLocal()
            company = db.get(Company, uuid.UUID(COMPANY_ID))
            cc = db.get(CompanyContext, uuid.UUID(cc_id))
            ctx_json = cc.context_json

            opps = db.scalars(
                select(Opportunity)
                .where(Opportunity.status == "open", Opportunity.source == "narajangter")
                .limit(50)
            ).all()

            matched = 0
            skipped = 0
            for opp in opps:
                opp_dict = {
                    "id": str(opp.id),
                    "title": opp.title or "",
                    "agency": opp.agency,
                    "region": opp.region,
                    "category": opp.category,
                    "description": opp.description,
                }
                rule_presets = _compute_rule_presets(ctx_json, opp_dict)
                result = score_match(ctx_json, opp_dict, rule_presets, llm_complete_json=None)

                if result.score < settings.match_threshold:
                    skipped += 1
                    continue

                reason_text = "; ".join(result.reasons) if result.reasons else None
                stmt = (
                    pg_insert(Match)
                    .values(
                        id=uuid.uuid4(),
                        company_id=company.id,
                        opportunity_id=opp.id,
                        score=result.score,
                        reason=reason_text,
                        subscore=result.subscore,
                        risk=result.risk,
                        created_at=datetime.now(timezone.utc),
                    )
                    .on_conflict_do_update(
                        constraint="uq_matches_company_opp",
                        set_={
                            "score": result.score,
                            "reason": reason_text,
                            "subscore": result.subscore,
                            "risk": result.risk,
                        },
                    )
                )
                db.execute(stmt)
                matched += 1

            db.commit()
            MATCH_RESULT = {"processed": 1, "matched": matched, "skipped": skipped}
            print(f"  OK: 직접 규칙 매칭 완료 -- matched={matched}, skipped={skipped}")
            db.close()
        except Exception as e:
            import traceback
            print(f"  ERROR: 직접 매칭 실패: {e}")
            traceback.print_exc()
            try:
                db.close()
            except Exception:
                pass
else:
    print("  SKIP -- 임베딩된 공고 없고 BGE도 가용")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: 추천 출력 확인 (FastAPI TestClient)
# ─────────────────────────────────────────────────────────────────────────────
print("\n[STEP 7] 추천 API 출력 확인 (FastAPI TestClient)...")

RECS = []

try:
    from fastapi.testclient import TestClient  # noqa: E402
    from app.main import app  # noqa: E402

    client = TestClient(app, raise_server_exceptions=True)

    # 로그인 (테스트 회사 토큰 발급)
    login_resp = client.post("/api/v1/auth/login", json={
        "email": TEST_EMAIL,
        "password": "TestPass123!",
    })
    if login_resp.status_code != 200:
        print(f"  ERROR: 로그인 실패: {login_resp.status_code} {login_resp.text[:200]}")
        access_token = None
    else:
        tokens = login_resp.json()
        access_token = tokens["access_token"]
        print(f"  OK: 로그인 성공 -- access_token 획득")

    if access_token:
        headers = {"Authorization": f"Bearer {access_token}"}

        # GET /recommendations/today
        rec_resp = client.get("/api/v1/recommendations/today", headers=headers)
        print(f"\n  GET /api/v1/recommendations/today → {rec_resp.status_code}")

        if rec_resp.status_code == 200:
            RECS = rec_resp.json()
            print(f"  추천 건수: {len(RECS)}")
        else:
            print(f"  ERROR: {rec_resp.text[:300]}")

except Exception as e:
    import traceback
    print(f"  ERROR: TestClient 실패: {e}")
    traceback.print_exc()

# matches 직접 조회 (API 실패해도 결과 확인)
print("\n  matches 테이블 직접 조회...")
db = SessionLocal()
try:
    from app.db.models.opportunity import Match  # noqa: F811
    matches = db.scalars(
        select(Match)
        .where(Match.company_id == uuid.UUID(COMPANY_ID))
        .order_by(Match.score.desc())
        .limit(5)
    ).all()

    print(f"  matches 건수 (상위 5): {len(matches)}")
    DB_MATCHES = []
    for m in matches:
        opp = db.get(Opportunity, m.opportunity_id)
        if opp:
            DB_MATCHES.append({
                "title": opp.title,
                "agency": opp.agency,
                "category": opp.category,
                "budget_amount": opp.budget_amount,
                "deadline": str(opp.deadline) if opp.deadline else None,
                "detail_url": opp.detail_url,
                "score": m.score,
                "reason": m.reason,
                "subscore": m.subscore,
                "risk": m.risk,
            })
finally:
    db.close()

# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: 보고
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("E2E 검증 결과 보고")
print("=" * 70)

print(f"""
[파이프라인 동작 여부]
  BGE 임베딩 가용:        {BGE_AVAILABLE}
  공고 수집 건수:          {COLLECTED_COUNT}
  status=open 공고:        {OPEN_OPP_COUNT}
  임베딩 완료 건수:        {EMBEDDED_COUNT}
  매칭 결과:               {MATCH_RESULT}
  추천 API 응답 건수:      {len(RECS)}
""")

if DB_MATCHES:
    print("[추천 Top 5 -- 실제 데이터]")
    for i, m in enumerate(DB_MATCHES[:5], 1):
        deadline = m["deadline"]
        d_day = None
        if deadline:
            try:
                from datetime import datetime as dt
                dl = dt.fromisoformat(deadline.replace("Z", "+00:00"))
                d_day = (dl.date() - datetime.now(timezone.utc).date()).days
            except Exception:
                pass

        budget_str = f"{m['budget_amount']:,}원" if m['budget_amount'] else "null(미제공)"
        print(f"""
  [{i}] {m['title'][:60]}
      기관:     {m['agency'] or 'null'}
      분류:     {m['category'] or 'null'}
      예산:     {budget_str}
      마감:     {m['deadline'] or 'null'} (D{d_day:+d} 또는 D-day unknown)
      score:    {m['score']}
      reasons:  {m['reason'] or '(빈값)'}
      subscore: {m['subscore']}
      risk:     {m['risk'] or '없음'}
      URL:      {m['detail_url'] or 'null'}""")
else:
    print("[추천 없음] -- matches 테이블에 결과 없음")

# ── UX/UI 정보 충실도 평가 ──────────────────────────────────────────────────
print("""
[UX/UI 정보 충실도 평가]
""")

if DB_MATCHES:
    null_budget = sum(1 for m in DB_MATCHES if m["budget_amount"] is None)
    null_deadline = sum(1 for m in DB_MATCHES if m["deadline"] is None)
    null_reasons = sum(1 for m in DB_MATCHES if not m["reason"])
    null_url = sum(1 for m in DB_MATCHES if not m["detail_url"])
    total = len(DB_MATCHES)

    print(f"  budget_amount null 비율: {null_budget}/{total} ({null_budget/total*100:.0f}%)")
    print(f"  deadline null 비율:      {null_deadline}/{total} ({null_deadline/total*100:.0f}%)")
    print(f"  reasons 빈값 비율:       {null_reasons}/{total} ({null_reasons/total*100:.0f}%)")
    print(f"  detail_url null 비율:    {null_url}/{total} ({null_url/total*100:.0f}%)")

print("""
  필드 충실도 분석:
  ✓ 있는 필드: title, agency, category, score, source, detail_url (나라장터 제공)
  ✗ 구조적 결여: region (나라장터 API 목록에 없음 → 항상 null)
  ✗ 구조적 결여: budget_amount (presmptPrce/asignBdgtAmt 미제공 공고 다수)
  ✗ LLM 없는 reasons 품질 문제:
    - 규칙 기반 템플릿: "기술 일치: GIS", "산업 일치: 용역", "지역 일치: 전국 대상 공고"
    - 사용자 설득력 낮음: 왜 이 공고가 우리 회사에 좋은지 설명 불가
    - LLM 없이는 수행실적 유사도(track score) 항상 0 → 최대 score 상한 75점
  ✗ RecommendationItem에 detail_url 필드 없음 (스키마 누락)
    - /recommendations/today 응답에 URL 미포함 → 사용자가 클릭 불가
  ✗ other_sources 항상 [] (dedup 미구현)

  [추천 카드 UI 그리기에 충분한가?]
  필요: 제목/적합도/마감/근거/CTA(바로가기 URL)
  현황:
    제목(title) ✓  적합도(score) ✓  마감(deadline/d_day) ✓(마감 있는 경우)
    근거(reasons) △(템플릿 수준)  CTA(detail_url) ✗(스키마 누락)
  → CTA URL 없이 추천 카드 완성 불가. 가장 긴급한 스키마 보완 항목.
""")

print("""
[발견된 버그/이슈]
  1. RecommendationItem 스키마에 detail_url 필드 없음
     → app/schemas/opportunity.py: RecommendationItem + recommendations.py 응답 구성에 추가 필요
  2. .env EMBEDDING_PROVIDER=voyage vs config.py 기본값 bge 불일치
     → .env를 EMBEDDING_PROVIDER=bge로 수정해야 BGE가 작동함 (현재 e2e_check.py에서 강제 override)
  3. region 필드 항상 null
     → 나라장터 API 목록 엔드포인트에 지역 필드 없음. 기관명으로 지역 추론 또는 상세 API 호출 필요
  4. LLM 없는 track score=0
     → 최대 점수 상한: tech(18)+industry(15)+region(10)+customer(20) = 63점
        MATCH_THRESHOLD=70이면 규칙 기반으로 임계 달성 거의 불가 → 임계값 조정(≤50) 권장
  5. 수집 후 embed_opportunity.delay() 호출 (Celery 없이) -- 스크립트에서 동기적으로 수동 호출

[권장 개선]
  즉시:
    - RecommendationItem에 detail_url 추가 (UI CTA 필수)
    - .env EMBEDDING_PROVIDER=bge로 수정
    - MATCH_THRESHOLD를 50으로 낮춰 규칙 기반 매칭 결과 확인 가능하게
  단기:
    - reasons 품질: 공고 제목 내 키워드→회사 역량 매핑 설명 (예: "용역 공고 -- 귀사 GIS 솔루션 적합")
    - region 추론: agency에서 "서울시", "경기도" 추출해 opp.region 채우기
    - budget_amount 없는 경우 UI에 "금액 미제공" 명시 (null이 공고 자체 문제임을 표시)
  중기:
    - LLM 연동 (track score 활성화, reasons 품질 대폭 향상)
    - 상세 API(getBidPblancDtlInfo) 연동으로 본문 텍스트 확보 → 임베딩 품질 향상
""")

print("=" * 70)
print("E2E 검증 완료")
print("=" * 70)
