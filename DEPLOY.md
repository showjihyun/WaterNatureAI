# ☁️ 인터넷에 올리기 (배포 가이드)

> 목표: **설치 없이 링크만 열면 쓰는 테스트 서비스**를 만들기.

## 0. 먼저 알아야 할 것 — "Vercel만으로는 안 됩니다"

이 앱은 **4덩어리**라서, Vercel **한 곳**에 다 올릴 수 없어요. Vercel은 **웹 화면(프론트)** 전용입니다.

| 덩어리 | 무엇 | 어디에 올리나 |
|---|---|---|
| 🟨 웹 화면 (Next.js) | 사람이 보는 화면 | **Vercel** ✅ |
| 🟩 서버 (FastAPI) | 계산·API | **Railway / Render / Fly.io** (Vercel ✗) |
| 🟦 데이터베이스 (PostgreSQL **+ pgvector**) | 데이터·AI 벡터 | Railway / Render / **Neon** / Supabase |
| 🟦 캐시·큐 (Redis) | 작업 큐 | Railway / **Upstash** |
| ⚙️ 일꾼 (Celery worker+beat) | 매일 자동 수집·매칭 | 서버와 같은 호스트의 **별도 프로세스** |

> 왜 Vercel에 서버를 못 올리나요? FastAPI는 **계속 떠 있는 서버**이고, AI 임베딩 모델(**약 1.5~2GB**)을 메모리에 올립니다. Vercel의 서버리스 함수(용량·시간 제한)로는 불가능해요.

### 가장 간단한 추천 조합 (테스트용)
**Vercel**(프론트) + **Railway**(서버 + Postgres + Redis + 일꾼 한 프로젝트). — 아래는 이 조합 기준입니다. (Render도 동일 개념)

---

## 1. 🟩🟦 백엔드 올리기 (Railway)

1. [railway.app](https://railway.app) 가입 → **New Project**.
2. **+ New → Database → PostgreSQL** 추가. 생성 후 SQL 콘솔(또는 `psql`)에서 **pgvector 확장 켜기**:
   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```
   > ⚠️ 이 한 줄 안 하면 매칭(벡터 검색)이 깨집니다. (Neon·Supabase는 대시보드에서 pgvector 토글 제공)
3. **+ New → Database → Redis** 추가.
4. **+ New → GitHub Repo** → 이 저장소 선택. 서비스 설정:
   - **Root Directory**: `backend`
   - **Start Command**: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **메모리(RAM)**: **2GB 이상** 권장 (임베딩 모델 때문 — 512MB 무료티어는 첫 부팅에 **메모리 부족(OOM)**으로 죽어요).
5. (자동 수집을 켜려면) **일꾼 서비스 2개**를 같은 repo로 더 추가 — Root `backend`, Start Command만 다르게:
   - 워커: `python -m celery -A app.core.celery_app.celery_app worker --loglevel=info`
   - 스케줄러: `python -m celery -A app.core.celery_app.celery_app beat --loglevel=info`
   > 처음엔 일꾼 없이 web만 올려 **화면·로그인부터 확인**하고, 나중에 추가해도 됩니다.
6. 배포 후 **마이그레이션** 1회 실행 (Railway 서비스 셸 또는 Start Command 앞에 `alembic upgrade head &&` 추가):
   ```bash
   alembic upgrade head
   ```
7. 백엔드 공개 주소(예: `https://bizradar-api.up.railway.app`)를 메모해 두세요 → 프론트에서 씁니다.

### 백엔드 환경변수 (Railway → Variables)
| 변수 | 값 | 비고 |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://...` | Railway Postgres가 주는 URL(드라이버를 `+psycopg`로) |
| `REDIS_URL` | `redis://...` | Railway Redis URL |
| `CORS_ORIGINS` | `https://여기-내-프론트.vercel.app` | **프론트 주소** (콤마로 여러 개) |
| `APP_ENV` | `production` | `local`이 아니어야 함 |
| `JWT_SECRET` | (랜덤 32자+) | 안 넣으면 부팅 거부 |
| `APP_SECRET_KEY` | (랜덤 32자+) | 〃 |
| `COOKIE_SECURE` | `true` | HTTPS 쿠키 |
| `COOKIE_SAMESITE` | `none` | **크로스도메인 로그인용**(아래 3번 참고) |
| `NARAJANGTER_SERVICE_KEY` 등 | (선택) | 실제 공고 수집 키 (공공데이터포털) |
| `ANTHROPIC_API_KEY` 등 | (선택) | AI 추천 근거 |

> 🔑 랜덤 키 만들기: `python -c "import secrets; print(secrets.token_urlsafe(48))"`

---

## 2. 🟨 프론트 올리기 (Vercel)

1. [vercel.com](https://vercel.com) 가입 → **Add New → Project** → 이 GitHub 저장소 선택.
2. **Root Directory** 를 **`frontend`** 로 지정 (모노레포라 꼭!).
3. Framework: **Next.js** 자동 감지 — 빌드 설정 그대로.
4. **Environment Variables** 에 추가:
   | 변수 | 값 |
   |---|---|
   | `NEXT_PUBLIC_API_BASE` | `https://여기-내-백엔드.up.railway.app/api/v1` |
   > 끝의 **`/api/v1`** 까지 포함! (없으면 전부 404)
5. **Deploy** → 끝나면 `https://내-앱.vercel.app` 주소가 나옵니다.
6. 이 주소를 **백엔드의 `CORS_ORIGINS`** 에 넣고 백엔드 재배포 → 양쪽이 서로를 알게 됩니다.
7. `README.md` 상단 "체험용 데모" 주소를 이 Vercel 주소로 교체.

---

## 3. 🔐 로그인(쿠키) 연결 — 가장 흔한 함정

로그인 토큰은 **httpOnly 쿠키**입니다. 프론트(`*.vercel.app`)와 백엔드(`*.railway.app`)가 **다른 도메인**이면 기본 설정(`SameSite=strict`)에선 쿠키가 안 실려 **로그인이 안 됩니다.**

**방법 A — 쿠키를 크로스사이트 허용 (간단)**
- 백엔드 env: `COOKIE_SAMESITE=none` + `COOKIE_SECURE=true` (위 표대로). HTTPS에서 동작.

**방법 B — 한 도메인처럼 보이게 프록시 (가장 깔끔, 권장)**
- `frontend/next.config.js` 에 rewrite로 `/api`를 백엔드로 프록시하면 브라우저가 **같은 출처**로 인식 → 쿠키 문제 사라짐:
  ```js
  async rewrites() {
    return [{ source: "/api/:path*", destination: "https://내-백엔드.up.railway.app/api/:path*" }];
  }
  ```
- 그리고 Vercel env를 `NEXT_PUBLIC_API_BASE=/api/v1` (상대경로)로. (이러면 `COOKIE_SAMESITE`는 기본값이어도 됨)
- 단, 모든 API가 Vercel을 한 번 거쳐 약간 느려집니다(테스트엔 무방).

---

## 4. ✅ 배포 후 점검 (순서대로)
1. `https://내-백엔드/health` → `{"status":"ok"}` 나오나?
2. 프론트 열기 → 로그인 화면 **"목 데이터 대시보드 바로가기"** 동작하나? (백엔드 없이 화면만 확인)
3. 회원가입·로그인 되나? (안 되면 → 3번 쿠키, 또는 `CORS_ORIGINS` 오타)
4. (일꾼 켰으면) 잠시 후 대시보드에 추천이 채워지나? (안 차면 공공데이터 키/워커 로그 확인)

---

## 5. 💸 비용 현실 (테스트 기준 대략)
- **Vercel**: 프론트는 **무료**(Hobby).
- **백엔드 RAM 2GB**: 임베딩 모델 때문에 무료론 부족 → Railway/Render에서 **월 ~$5~25** 예상.
- **Postgres·Redis**: 소규모 무료~소액. (Neon Postgres + Upstash Redis는 무료 구간 있음)
- 💡 비용을 더 줄이려면: 일꾼(자동수집) 끄고 **web+DB만** 띄워 화면·로그인·목데이터 위주로 데모.

---

## 6. 🔒 보안 (배포 시 필수)
- `.env`·키는 **코드/깃에 올리지 말고** 각 플랫폼의 **Variables/Secrets** 에만.
- `APP_ENV`는 `local` 금지, `JWT_SECRET`·`APP_SECRET_KEY`는 **강한 랜덤값**(안 그러면 서버가 부팅 거부).
- 사업 문서·실데이터(PII)는 공개 배포본에 포함하지 마세요(이 repo는 `.gitignore`로 이미 제외).
