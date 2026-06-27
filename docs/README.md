# BizRadar AI — 기술 문서

중소기업용 **AI 사업개발(BD) 에이전트** BizRadar AI의 아키텍처·데이터·API 설계 문서.

## 📂 설계 (04-architecture)

| 문서 | 설명 |
|---|---|
| [architecture.md](04-architecture/architecture.md) | 시스템·에이전트·DB·배포 아키텍처 |
| [auth-onboarding.md](04-architecture/auth-onboarding.md) | 인증/온보딩 (회원가입·로그인·JWT·온보딩 상태머신) |
| [company-brain.md](04-architecture/company-brain.md) | Company Brain (프로필+문서 → Company Context 생성·임베딩) |
| [data-ingestion.md](04-architecture/data-ingestion.md) | 데이터 소스 카탈로그 & 수집·갱신 설계 (API/스크래핑/증분/인증키) |
| [p0-source-spec.md](04-architecture/p0-source-spec.md) | P0 4종(나라장터·기업마당·K-Startup·NTIS) API 상세 스펙 & 통합 매핑 |
| [db-schema-opportunities.md](04-architecture/db-schema-opportunities.md) | opportunities 통합 스키마 + 마이그레이션(DDL/Alembic/SQLAlchemy) |
| [collector-narajangter.md](04-architecture/collector-narajangter.md) | 나라장터 Collector 설계 (증분/정규화/UPSERT/재임베딩/의사코드) |
| [collector-base-bizinfo.md](04-architecture/collector-base-bizinfo.md) | BaseCollector 추상화 + 기업마당 Collector (상세 본문 추출 2단계) |
| [collector-kstartup-ntis.md](04-architecture/collector-kstartup-ntis.md) | K-Startup·NTIS Collector (날짜필터 증분 / API·스크래핑 2경로) |
| [embed-worker.md](04-architecture/embed-worker.md) | embed_opportunity 워커 (임베딩 모델·벡터 upsert·재임베딩) |
| [matching-engine.md](04-architecture/matching-engine.md) | Matching 엔진 (검색 prefilter + 가중 스코어링 + 설명 근거) |
| [display-dedup.md](04-architecture/display-dedup.md) | 표시단계 dedup (다중소스 중복 군집화·대표 선정) |
| [daily-briefing.md](04-architecture/daily-briefing.md) | Daily Briefing / 카카오 알림 (알림톡·Top3·도달추적·SMS폴백) |
| [dashboard-api.md](04-architecture/dashboard-api.md) | 대시보드/API 표면 (추천조회·상세·액션·통계·설정, action_type 표준) |
| [billing.md](04-architecture/billing.md) | 결제(Toss) 기본 틀 (정기결제 스캐폴딩 — 사업자 확보 후 라이브) |
| [coding-testing.md](04-architecture/coding-testing.md) | 코딩·테스트 규약 + AI 모델 정책 |

## 📡 데이터 API 레퍼런스 (06-data api ref)

| 문서 | 설명 |
|---|---|
| [README-narajangter-api.md](<06-data api ref/README-narajangter-api.md>) | 나라장터 3종 API (키·엔드포인트·필드 매핑, live 검증) |
| [카카오 메시지 API 가이드](<06-data api ref/카카오_메시지API_나에게보내기_가이드.md>) | 카카오 '나에게 보내기' 메시지 API 연동 가이드 |

> 🔑 키·시크릿은 문서에 평문으로 넣지 않는다. 모든 자격증명은 `.env`(미추적)로만 주입한다.
