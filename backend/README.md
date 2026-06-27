# BizRadar AI — Backend (MVP 스캐폴드)

권장 첫 구현 경로(**P0 기반 → 나라장터 수집 → embed/매칭 → 대시보드**)의 코드 골격.
설계 정본: [`../docs/00-overview/architecture-roadmap.md`](../docs/00-overview/architecture-roadmap.md).
코딩·테스트 규약(모델 정책 포함): [`../docs/04-architecture/coding-testing.md`](../docs/04-architecture/coding-testing.md).

## 스택
FastAPI · SQLAlchemy 2.0 · Alembic · Celery + Redis · PostgreSQL · Qdrant · JWT/Argon2.

## 구조
```
app/
  core/        config·security(JWT/Argon2)·celery_app(Beat 스케줄)
  db/          base(세션)·models/(전 테이블)
  api/         deps(인증·company 격리)·v1/(auth·recommendations·opportunities·actions·stats·settings)
  schemas/     pydantic 스키마
  services/
    auth_service.py
    collectors/  base(BaseCollector)·narajangter(1순위)·client·normalize·registry·tasks
    embedding/   provider(voyage/bge)·qdrant·tasks(embed_opportunity)
    matching/    engine(retrieval+scoring)·tasks(sweep·run_daily)
    dedup/       tasks(run)                ← 스텁
    notifications/ provider(SOLAPI)·tasks   ← 스텁
    billing/     provider(Toss, test)       ← 스텁
    company_brain/ service                  ← 스텁
alembic/       env·versions(autogenerate)
```

## 로컬 실행
```bash
cp .env.example .env            # 키/URL 채우기
pip install -e ".[dev]"
docker compose -f docker-compose.dev.yml up -d   # PostgreSQL·Redis·Qdrant
alembic upgrade head                              # 스키마(0001_init: 전 테이블+시드)
uvicorn app.main:app --reload                     # API
celery -A app.core.celery_app.celery_app worker -B --loglevel=info   # 워커+Beat
```
> 마이그레이션은 이미 `alembic/versions/0001_init`에 존재. 모델 변경 시에만
> `alembic revision --autogenerate -m "..."` 후 [db-schema §9~§11] 수동 보강 반영.

## 테스트 & 품질 게이트
CI 순서(coding-testing §5): **ruff → mypy → pytest**. 머지 전 모두 통과.
```bash
ruff check app/ tests/ alembic/        # 린트(line 100)
mypy                                    # 타입 — 게이트 범위=app/ (pyproject files 고정)
pytest tests/unit -q                    # 단위(DB 불필요)
# 통합/스모크는 환경변수로 활성:
TEST_DATABASE_URL="postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar_test" \
  pytest tests/integration -q           # 통합(없으면 자동 skip)
pytest tests/smoke -q                   # 실 API 스모크(.env 키 있으면 동작, 없으면 skip)
```
- **mypy 게이트 = `app/` 만**(프로덕션 코드). `tests/`는 mock/fixture 특성상 best-effort 비대상.
- K-Startup/NTIS 테스트는 운영 미투입(키 미확보)이라 pytest `addopts`에서 `--ignore` 제외.

## 구현 상태
| 영역 | 상태 |
|---|---|
| 인증/온보딩(register/login/refresh) | 동작 골격 |
| 나라장터 수집기(증분·UPSERT·변경감지) | 동작 골격(필드명 ⚠️ 검증) |
| embed 워커(Qdrant) | 골격(provider 연결 TODO) |
| 매칭(sweep·retrieval) | 골격(LLM 스코어링 TODO) |
| 대시보드 API(조회·액션·통계·설정) | 동작 골격 |
| dedup·briefing·billing·company_brain | **스텁(TODO)** |

## ⚠️ 구현 전 검증/외부 의존
[`../docs/05-spikes/blocker-resolution.md`](../docs/05-spikes/blocker-resolution.md) — 응답 필드명·NTIS(✅15074634)·임베딩 PoC·카카오(SOLAPI)·**사업자등록**(결제+카카오+SMS 공통).

## 표준 일일 타임라인(Beat, KST)
08:50 sweep → 09:00 수집(run_all=나라장터)·임베딩 → 09:05 낙찰(run_scsbid) →
09:30 dedup → 10:00 매칭 → 11:00 브리핑. (수집 시각은 COLLECT_SCHEDULE_HOUR/MINUTE)
