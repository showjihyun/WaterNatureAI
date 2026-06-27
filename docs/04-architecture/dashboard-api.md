# 대시보드 / API 표면 설계

> 프론트(Next.js)와 백엔드(FastAPI) 간 REST API. 추천 조회·상세·액션(관심/참여)·통계·설정. FR-009 등.
> 관련: [인증/온보딩](auth-onboarding.md) · [Matching 엔진](matching-engine.md) · [표시 dedup](display-dedup.md) · [Daily Briefing](daily-briefing.md) · [Architecture §2 Pages](architecture.md) · [PRD North Star](../02-product/prd.md)
> **작성 기준일:** 2026-06-20

---

## 1. 공통 규약

- **Base:** `/api/v1`. JSON. 인증: `Authorization: Bearer {access}`([auth §4](auth-onboarding.md)).
- **테넌트 격리:** 모든 응답은 토큰의 `company_id` 범위로 자동 필터.
- **페이지네이션:** `?page=&size=`(또는 cursor). 응답에 `total`/`page`/`size`.
- **에러 envelope:** `{ "error": { "code": "...", "message": "...", "details": {} } }`.
- **시간:** ISO8601(KST 오프셋 포함).

---

## 2. action_type 표준 (H1 해소 — North Star 퍼널)

`user_opportunity_actions.action_type` 값 집합을 고정한다. ([PRD §3 퍼널](../02-product/prd.md): Recommended→Opened→Reviewed→Interested→Participated)

| action_type | 의미 | 퍼널 단계 | 발생 |
|---|---|---|---|
| `notified` | 알림 발송됨 | Recommended | Daily Briefing(시스템) |
| `opened` | 추천/알림 클릭, 상세 진입 | Opened | 상세 조회 / 카카오 링크 |
| `reviewed` | (선택) 충분 열람·명시 검토 | Reviewed | 상세 체류/액션(파생 가능) |
| `saved` | **관심 등록**(FR: 관심 사업 저장) | Interested | 사용자 액션 |
| `participated` | 참여 표시 | Participated | 사용자 액션 |

> 저장은 TEXT + **문서화된 값 집합**(소스 ENUM 교훈상 ENUM 회피). 선택적 CHECK 제약 가능([db-schema 색인 `0009`](db-schema-opportunities.md)). `saved` 해제는 별도 액션이 아니라 행 삭제/플래그로 처리.

---

## 3. 엔드포인트

| 메서드 | 경로 | 설명 | 매핑 |
|---|---|---|---|
| GET | `/recommendations/today` | 오늘의 추천 **Top 5**(대시보드) | matches(canonical, score desc) |
| GET | `/opportunities` | 추천 목록 조회·필터·정렬 | **FR-009** |
| GET | `/opportunities/{id}` | 공고 상세 + 적합도/근거 + 다른 출처 | matches·dedup |
| POST | `/opportunities/{id}/actions` | 액션 기록 `{type}` | user_opportunity_actions |
| DELETE | `/opportunities/{id}/actions/saved` | 관심 해제 | — |
| GET | `/dashboard/stats` | 퍼널 통계(기간별) | 액션 집계 |
| GET·PUT | `/company/profile` | 프로필 조회/수정(FR-003) | [auth-onboarding](auth-onboarding.md) |
| POST | `/company/documents` | 문서 업로드(FR-004) | [company-brain](company-brain.md) |
| GET·PUT | `/settings/notification` | 수신설정 | notification_settings |
| GET | `/settings/billing` | 구독 상태 | [billing](billing.md) |

> 인증/회사 프로필/문서 업로드 API 상세는 [auth-onboarding §8](auth-onboarding.md). 본 문서는 **추천·조회·액션·통계·설정**에 집중.

---

## 4. 추천 조회 (FR-009)

`GET /opportunities`

**쿼리:** `agency`, `budget_min`, `budget_max`, `deadline_before`, `min_score`, `sort`(기본 `score_desc`), `page`, `size`
**규칙:** `is_canonical=TRUE` + `status=open` + 해당 company의 `matches`만. 기본 정렬 적합도 내림차순.

```jsonc
// 200
{
  "items": [{
    "opportunity_id": "...",
    "title": "AI 기반 공간정보 분석 플랫폼 구축",
    "agency": "한국국토정보공사",
    "category": "용역",
    "budget_amount": 350000000,
    "deadline": "2026-07-01T18:00:00+09:00",
    "d_day": 13,
    "score": 92,
    "reasons": ["LX 디지털트윈 수행실적 유사", "발주기관 경험 보유"],
    "saved": false,
    "source": "narajangter",
    "other_sources": ["bizinfo"]        // dedup 군집의 다른 출처
  }],
  "total": 37, "page": 1, "size": 20
}
```

`GET /recommendations/today` = 위와 동일 형식, 오늘자 Top 5(대시보드용). 카카오는 Top 3([daily-briefing](daily-briefing.md)).

---

## 5. 상세 & 액션

`GET /opportunities/{id}` → 공고 전체 + `match`(score/reasons/subscore/risk) + `other_sources`(dedup 군집 출처·링크) + `actions`(현재 company의 saved 등). 진입 시 `opened` 기록(또는 클라이언트가 POST).

`POST /opportunities/{id}/actions`
```jsonc
// req
{ "type": "saved" }       // opened | reviewed | saved | participated
// 200
{ "ok": true, "action_type": "saved", "created_at": "..." }
```
- 멱등: 동일 (company, opportunity, type) 중복은 1건 유지(또는 최신 갱신).
- 카카오 딥링크 클릭 → 상세 진입 → `opened`(퍼널 Opened) 기록.

---

## 6. 통계 (대시보드)

`GET /dashboard/stats?from=&to=`
```jsonc
{
  "recommended": 120,   // 추천(matches) 수 — 웹 퍼널 분모 (is_canonical=TRUE, status=open)
  "opened": 48,         // Opportunity Click Rate 분자
  "saved": 14,          // Saved Opportunity Rate
  "participated": 6,    // Participation Rate (North Star)
  "rates": { "open": 0.40, "save": 0.20, "participate": 0.10 }
}
```
- `recommended` = 해당 company의 `matches` 중 `Opportunity.is_canonical=TRUE AND status='open'` 건수 (`/recommendations/today` 와 동일 필터, limit 없이 count). `Match.created_at` 기준으로 `from`/`to` 기간 필터 적용.
- 카카오 Daily Briefing 발송(`notified` 액션) 기반 알림 퍼널은 웹 퍼널과 별개이며 `recommended` 분모에 포함되지 않는다(카카오는 test-mode/미발송 상태).
- `opened`/`saved`/`participated`는 `user_opportunity_actions` 집계(`created_at` 기준 기간 필터).
- MVP 성공기준(클릭률 40%/관심 20%/참여 10%)과 직접 매핑([service-analysis §6](../00-overview/service-analysis.md)).
- MRR·구독자수 등 비즈니스 지표는 [billing](billing.md) 데이터로 별도 산출.

---

## 7. 설정

- `GET·PUT /settings/notification` → `notification_settings`(enabled/channel/send_hour/send_empty).
- `GET /settings/billing` → 구독 상태/플랜/다음 결제일(읽기). 결제수단 등록·해지는 [billing](billing.md) 플로우(현재 테스트 모드).

---

## 8. 엣지 케이스

| 케이스 | 처리 |
|---|---|
| 온보딩 미완료 | 추천 비어있음 + 온보딩 유도(`/me.onboarding_status`) |
| 구독 비활성 | 조회는 제한 노출/블러 또는 결제 유도(정책), Briefing 미발송 |
| 비대표(dedup) 공고 직접 요청 | 대표(`is_canonical`)로 리다이렉트/병합 노출 |
| 마감 지난 공고 | 목록 기본 제외(status), 상세는 열람 가능(closed 표기) |
| 타 회사 리소스 요청 | 404/403(테넌트 격리) |
| 액션 중복 | 멱등 처리 |

---

## 9. 검증 & 다음 단계
- [ ] `action_type` 표준 값 + (선택) CHECK 제약 마이그레이션
- [ ] 추천 조회 필터/정렬·페이지네이션·테넌트 격리 테스트
- [ ] 상세 `opened` 기록 위치(서버 자동 vs 클라이언트) 결정
- [ ] 통계 집계 쿼리(퍼널) + 캐싱
- [ ] OpenAPI(스웨거) 스키마 생성 → 프론트 타입 동기화
- [ ] 구독 게이트(노출 정책) 확정([billing](billing.md) trial 정책)
