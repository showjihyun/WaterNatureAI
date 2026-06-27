# 코딩 · 테스트 규약

> 백엔드(`backend/`) 개발·테스트 컨벤션과 **AI 모델 사용 정책**.
> 관련: [아키텍처 로드맵](../00-overview/architecture-roadmap.md) · [db-schema](db-schema-opportunities.md) · backend [README](../../backend/README.md)
> **작성 기준일:** 2026-06-18

---

## 1. AI 모델 정책 (개발·테스트 vs 제품) ⭐

개발/테스트에 쓰는 모델과, 제품(런타임)에 쓰는 모델을 **분리**한다.

| 용도 | 모델 | 비고 |
|---|---|---|
| **결정론적 코딩·테스트** (스캐폴딩·리팩터·버그픽스·테스트 작성/실행·마이그레이션·CI 수정) | **Claude Sonnet 4.6** (`claude-sonnet-4-6`) | 반복·결정론적 작업은 속도·비용 효율 우선 → **Sonnet 4.6 사용** |
| 복잡 설계·아키텍처 판단·정합성 리뷰 | Claude Opus 4.8 (`claude-opus-4-8`) | 깊은 추론이 필요한 비결정 작업 |
| **제품 런타임 LLM** (매칭 근거 생성·Company Context 추출·브리핑 요약) | Claude Opus 4.8 (`claude-opus-4-8`) | 근거 품질·맥락 판단 중요 ([matching-engine](matching-engine.md), [company-brain](company-brain.md)) |
| 제품 임베딩 | voyage-4 / BGE-M3-ko | [embed-worker](embed-worker.md), [blocker-resolution](../05-spikes/blocker-resolution.md) |

> **규칙:** 명확한 사양이 있는 **결정론적 코딩·테스트 작업은 기본적으로 Sonnet 4.6로 진행**한다. 모호한 설계·트레이드오프 판단이 끼면 Opus 4.8로 승격한다. 제품 내부에서 호출하는 LLM(설정 `LLM_MODEL`)은 개발 모델과 무관하게 Opus 4.8을 기본으로 둔다.

---

## 2. 코드 규약 (Python)

- Python 3.11+, **타입 힌트 필수**, `from __future__ import annotations`.
- 포맷·린트 **ruff**(line 100), 타입 **mypy**. SQLAlchemy 2.0 `Mapped[...]` 스타일.
- 네이밍: 모듈/함수 `snake_case`, 클래스 `PascalCase`, 상수 `UPPER`.
- 주석/문서: 한국어 허용. 외부 의존·미확정은 `TODO(검증):`로 표기(명세/키/심사).
- 설정은 `app.core.config.settings` 한 곳(.env). 비밀키는 Secret Manager.
- DB 접근은 모델/세션 통해서만. 원시 SQL은 인덱스/함수 등 불가피한 경우만.

---

## 3. 테스트 전략 (pytest)

| 레벨 | 대상 | 예 |
|---|---|---|
| 단위 | 순수 로직 | `normalize`(parse_kst/parse_won/sha256_norm), `security`(JWT/해시), 매칭 sub-score 규칙 |
| 통합 | DB·repo | UPSERT·content_hash 변경감지 왕복, 테넌트 격리(타 회사 차단) |
| 계약 | 외부 API | 수집기 클라이언트 모킹(페이징 종료·5xx 재시도·resultCode 분기) |
| E2E | 파이프라인 | (샌드박스 키) 1일 윈도우 수집→임베딩→매칭→조회 |

- 외부 API/LLM/카카오/Toss는 **모킹**(실호출 금지, 키 없는 CI에서도 통과).
- 멱등성(수집 재실행·embed 스킵·알림 1일1회) 회귀 테스트 필수.
- 커버리지 우선순위: 수집 정규화·UPSERT > 인증·격리 > API 조회 > 스텁 영역.

---

## 4. 마이그레이션 규약

- 모델-퍼스트 `alembic revision --autogenerate` 후, [db-schema §9~§11](db-schema-opportunities.md)의 **수동 보강**(sweep 함수·부분 인덱스·시드) 반영.
- 적용 순서는 의존성 기준(0001→0002→0003→0004→0006→0007→0005→0008). 운영 DDL은 db-schema 정본 대조.

---

## 5. CI 게이트 (권장)
`ruff` → `mypy` → `pytest`(외부 모킹) 통과 시 머지. 결정론적 수정·테스트는 §1에 따라 Sonnet 4.6로 작업.
