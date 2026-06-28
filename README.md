# WaterNature AI 🛰️ — 공공사업 추천 에이전트

> **우리 회사가 "딸 수 있는" 공공사업만 매일 AI가 골라줍니다.**
> 입찰·정부지원사업·R&D 과제를 자동으로 모아, 회사 역량에 맞는 것만 적합도순으로 추천하는 서비스예요.

이 문서는 **개발을 잘 모르는 분도** 순서대로 따라 하면 내 컴퓨터에서 직접 실행해볼 수 있게 만들었습니다. 설치까지 보통 **10~15분** 걸립니다.

---

## 📦 이게 무엇인가요? (1분 설명)

- **회사 정보를 입력하면**(업종·기술·실적 등) AI가 회사를 이해하고,
- **여러 공공 사이트의 사업 공고**(나라장터·K-Startup·NTIS 등)를 매일 자동으로 모아서,
- **우리 회사에 잘 맞는 공고만** 적합도 점수와 함께 추천하고, **마감 임박·카카오 알림**도 보내줍니다.

화면(웹)과 서버, 데이터베이스로 이루어진 **3덩어리** 프로그램입니다:

| 덩어리 | 쉽게 말하면 | 기술 |
|---|---|---|
| **프론트엔드** | 사람이 보는 웹 화면 | Next.js (포트 3000) |
| **백엔드** | 화면 뒤에서 일하는 서버 | FastAPI (포트 8000) |
| **데이터베이스 + 캐시** | 데이터 저장소 | PostgreSQL · Redis (Docker) |

---

## 🧰 준비물 (처음 한 번만 설치)

아래 3개를 먼저 설치하세요. 이미 있으면 건너뛰면 됩니다.

| 프로그램 | 용도 | 다운로드 | 설치 확인 명령 |
|---|---|---|---|
| **Docker Desktop** | 데이터베이스를 손쉽게 실행 | https://www.docker.com/products/docker-desktop/ | `docker --version` |
| **Python 3.11+** | 백엔드 서버 실행 | https://www.python.org/downloads/ | `python --version` |
| **Node.js 18+** | 웹 화면 실행 | https://nodejs.org/ | `node --version` |

> 💡 **설치 확인 명령**을 터미널(Windows는 PowerShell, Mac은 터미널)에 입력했을 때 버전 숫자가 나오면 성공입니다.

---

## 🚀 실행하기 (순서대로 복사-붙여넣기)

> 터미널 창을 **여러 개** 열어두면 편합니다. (데이터베이스 / 백엔드 / 프론트엔드)

### 1단계 — 코드 내려받기

```bash
git clone https://github.com/showjihyun/WaterNatureAI.git
cd WaterNatureAI
```

### 2단계 — 데이터베이스 켜기 (Docker)

Docker Desktop을 먼저 실행해 두고:

```bash
cd backend
docker compose -f docker-compose.dev.yml up -d
```

> PostgreSQL(5433)·Redis(6379)가 백그라운드로 뜹니다. `docker ps` 로 두 개가 떠 있으면 OK.

### 3단계 — 백엔드(서버) 켜기

같은 `backend` 폴더에서:

```bash
# (1) 가상환경 만들기 — 처음 한 번만
python -m venv .venv

# (2) 가상환경 켜기   ※ Windows
.venv\Scripts\activate
#                    ※ Mac / Linux 는 아래
# source .venv/bin/activate

# (3) 라이브러리 설치 — 처음 한 번만 (몇 분 걸립니다)
pip install -e .

# (4) 설정 파일 만들기 — 처음 한 번만   ※ Windows
copy .env.example .env
#                                      ※ Mac / Linux 는: cp .env.example .env

# (5) 데이터베이스 표 만들기 — 처음 한 번만
alembic upgrade head

# (6) 서버 켜기 (이 창은 켜둔 채로)
uvicorn app.main:app --reload --port 8000
```

> ✅ 마지막에 `Uvicorn running on http://127.0.0.1:8000` 가 보이면 서버 성공.
> 브라우저로 http://localhost:8000/health 를 열어 `{"status":"ok"}` 가 나오면 정상입니다.

### 4단계 — 프론트엔드(웹 화면) 켜기

**새 터미널 창**을 열고:

```bash
cd WaterNatureAI/frontend
npm install        # 처음 한 번만 (몇 분 걸립니다)
npm run dev        # 화면 켜기 (이 창도 켜둔 채로)
```

> ✅ `Local: http://localhost:3000` 같은 줄이 보이면 성공.
> ⚠️ 3000번이 이미 쓰이면 자동으로 3001 등으로 뜹니다(터미널 메시지 확인). 그 경우엔 아래 [문제 해결](#-자주-막히는-곳-문제-해결)을 참고하세요.

### 5단계 — 열어보기 🎉

브라우저에서 **http://localhost:3000** 접속!

- **그냥 둘러보기:** 로그인 화면의 **"목 데이터 대시보드 바로가기"** 를 누르면 가짜 데이터로 화면을 바로 볼 수 있어요.
- **직접 써보기:** **회원가입** → 회사 프로필 입력(온보딩) → 대시보드에서 추천 확인.

---

## ⚙️ (선택) 실제 데이터·AI 기능 켜기

키 없이도 화면은 돌아가지만, **실제 공고 데이터·AI 근거·카카오 알림**을 쓰려면 키가 필요합니다.
모든 키는 **`backend/.env` 파일에만** 넣습니다. (이 파일은 절대 공개되지 않습니다 — 아래 [보안](#-보안-중요) 참고)

| 기능 | `.env` 항목 | 발급처 |
|---|---|---|
| **공고 수집**(나라장터 등) | `NARAJANGTER_SERVICE_KEY` 등 | [공공데이터포털 data.go.kr](https://www.data.go.kr) (무료) |
| **AI 추천 근거**(설명 생성) | `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` | 각 AI 제공사 (또는 화면 **설정 → AI 공급자**에서 입력) |
| **카카오 알림톡** | 화면 **설정 → 카카오 발신 설정**에서 입력 | [SOLAPI](https://solapi.com) + 사업자등록 |
| **결제(Toss)** | `TOSS_CLIENT_KEY` / `TOSS_SECRET_KEY` | [토스페이먼츠](https://www.tosspayments.com) |

> 키를 `.env`에 넣은 뒤에는 **백엔드 서버를 한 번 재시작**해야 적용됩니다(서버 창에서 `Ctrl+C` 후 6단계 다시 실행).

### (선택) 매일 자동 수집·알림 켜기

공고를 매일 자동으로 모으려면 **새 터미널**에서 작업 워커를 켜세요(가상환경 켠 상태로):

```bash
cd backend
celery -A app.core.celery_app.celery_app worker -B --loglevel=info
```

> 한국시간 기준 매일 오전에 수집→매칭→브리핑이 자동 실행됩니다. (한 번만 테스트로 모으고 싶으면 워커만 켜도 됩니다.)

---

## ❓ 자주 막히는 곳 (문제 해결)

| 증상 | 해결 |
|---|---|
| **백엔드가 DB 연결 실패 / 500 에러** | Docker Desktop이 켜져 있는지, `docker ps`에 postgres·redis 가 떠 있는지 확인. 멈췄으면 `docker compose -f backend/docker-compose.dev.yml up -d` |
| **코드를 고쳤는데 안 바뀜** | 서버는 자동 반영(`--reload`)되지만, 안 되면 백엔드 창 `Ctrl+C` 후 다시 켜기. 프론트는 보통 자동 반영. |
| **프론트가 3000이 아닌 3001로 떴어요** | 백엔드 `backend/.env`의 `CORS_ORIGINS` 에 `http://localhost:3001` 을 콤마로 추가하고 백엔드 재시작. (로그인/저장이 안 되면 대부분 이 문제) |
| **로그인/회원가입이 안 됨** | (1) 백엔드가 떠 있는지(8000) (2) 프론트 포트가 CORS에 포함됐는지 확인. |
| **`alembic`·`uvicorn` 명령을 못 찾음** | 가상환경이 켜져 있는지 확인(프롬프트 앞에 `(.venv)` 표시). 안 켜졌으면 3단계 (2)번 다시. |
| **추천 공고가 0건** | 아직 수집된 데이터가 없어서예요. "목 데이터" 로 먼저 둘러보거나, 위 [실제 데이터 켜기](#️-선택-실제-데이터ai-기능-켜기)로 공공데이터 키를 넣고 수집하세요. |

---

## 📁 폴더 구조 (간단히)

```
WaterNatureAI/
├─ backend/        FastAPI 서버 (Python)
│  ├─ app/         실제 코드 (api·services·db·core)
│  ├─ alembic/     데이터베이스 표 정의
│  ├─ .env         ← 내 키/설정 (직접 만듦, 공개 안 됨)
│  └─ docker-compose.dev.yml   DB·Redis 실행 설정
├─ frontend/       Next.js 웹 화면 (TypeScript)
│  └─ src/         페이지·컴포넌트
└─ docs/           기술 설계 문서
```

---

## 🔒 보안 (중요)

- **비밀 키는 절대 코드/깃에 올리지 마세요.** 모든 키는 `backend/.env` · `frontend/.env.local` 에만 넣습니다. 이 파일들은 `.gitignore`로 공개에서 제외되어 있고, 실수로 올리지 않도록 **pre-commit 안전장치**도 들어 있습니다.
- 비밀번호는 Argon2로 안전하게 저장되고, 로그인 토큰은 httpOnly 쿠키로 보호됩니다.
- 운영 배포 시에는 `.env`의 `APP_ENV`를 `local`이 아닌 값으로 바꾸고 `JWT_SECRET`·`APP_SECRET_KEY`를 **강한 랜덤값(32자 이상)** 으로 설정하세요(미설정 시 서버가 안전을 위해 부팅을 거부합니다).

---

## 🧑‍💻 (개발자용) 테스트

```bash
cd backend
pytest tests/unit -q      # 단위 테스트 (DB 불필요)
ruff check app/           # 코드 스타일 검사
```

자세한 설계·아키텍처는 [`docs/`](docs/) 폴더를 참고하세요.

---

## 📜 라이선스

루트의 [`LICENSE`](LICENSE) 파일을 참고하세요.
