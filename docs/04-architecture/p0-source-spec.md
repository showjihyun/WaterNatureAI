# P0 데이터 소스 — API 상세 스펙 & 통합 매핑

> P0 4종(**나라장터 · 기업마당 · K-Startup · NTIS**)의 구현용 레퍼런스.
> 상위 전략: [데이터 소스 카탈로그 & 수집·갱신 설계](data-ingestion.md)
> **작성 기준일:** 2026-06-17

**범례:** ✅ 출처로 확인 · ⚠️ 작성 시점 추정, 구현 전 명세/ Swagger로 재확인 필요

| 소스 | 커버 공고유형 | 인증 | 갱신 | 증분 키 |
|---|---|---|---|---|
| 나라장터 | 입찰·조달(용역/물품/공사/외자) | data.go.kr 키 | 실시간 ✅ | 게시일시(`inqryBgnDt~inqryEndDt`) |
| 기업마당 | 정부지원사업(그랜트) | bizinfo 자체 키 | 일 단위 | 등록일(`creatPnttm`) |
| K-Startup | 창업 지원사업 공고 | data.go.kr 키 | 일 단위 | 접수시작일/등록일 |
| NTIS | R&D 과제 통합공고 | NTIS 키 ⚠️ | 수시 | 공고일자 |

---

## 1. 나라장터 입찰공고정보서비스

- **출처:** data.go.kr `15129394` ✅ / Base URL: `https://apis.data.go.kr/1230000/ad/BidPublicInfoService` ✅ (⚠️ **`/ad` prefix 필수** — 누락 시 404, live 검증 2026-06-18). 낙찰=`/as/ScsbidInfoService`, 표준=`/ao/PubDataOpnStdService`. 상세·필드매핑 → [데이터 API 레퍼런스](<../06-data api ref/README-narajangter-api.md>)
- **갱신:** 실시간 ✅ · **요청제한:** 개발 1,000/일, 운영 상향가능

### 오퍼레이션 (업무유형별로 분리 — 반드시 유형에 맞는 것 호출) ✅

| 오퍼레이션 | 대상 |
|---|---|
| `getBidPblancListInfoThng` | 물품 |
| `getBidPblancListInfoServc` | 용역 |
| `getBidPblancListInfoCnstwk` | 공사 |
| `getBidPblancListInfoFrgcpt` | 외자 |
| `getBidPblancListInfo...PPSSrch` | 나라장터 검색조건 버전(필요 시) |

### 요청 파라미터 ✅

| 파라미터 | 설명 |
|---|---|
| `serviceKey` | 인증키(URL-encoded) |
| `inqryDiv` | 조회구분 (1 = 공고게시일시 기준) |
| `inqryBgnDt` / `inqryEndDt` | 조회 시작/종료 일시 — `YYYYMMDDHHMM` |
| `pageNo` / `numOfRows` | 페이지 / 건수(최대 1000) |
| `type` | `json` 또는 `xml` |
| `indstrytyCd` | (선택) 업종코드 |
| `bidNtceNm` | (선택) 공고명 검색 |

### 주요 응답 필드 ⚠️(명세 재확인)

| 필드 | 의미 | → 통합 |
|---|---|---|
| `bidNtceNo` | 입찰공고번호 | `source_uid`(+`bidNtceOrd`) |
| `bidNtceOrd` | 공고 차수(정정) | 변경추적 |
| `bidNtceNm` | 공고명 | `title` |
| `ntceInsttNm` | 공고기관 | `agency` |
| `dminsttNm` | 수요기관 | `agency`(보조) |
| `bidNtceDt` | 공고게시일시 | `posted_at` |
| `bidClseDt` | 입찰마감일시 | `deadline` |
| `presmptPrce` / `asignBdgtAmt` | 추정가격 / 배정예산 | `budget` |
| `bidNtceDtlUrl` | 상세 URL | `detail_url` |

### 증분 전략
`inqryDiv=1`, `inqryBgnDt = last_success − 2일(버퍼)`, `inqryEndDt = now`. 4개 업무유형 각각 페이지 끝까지. 정정공고는 `bidNtceOrd`로 차수 추적(최신 차수 유효 + 이력 보존).

---

## 2. 기업마당(Bizinfo) 지원사업정보 API

- **출처:** bizinfo 정책정보 개방 ✅ / 요청 URL: `https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do` ✅
- **인증:** 기업마당 자체 발급(이메일 수령) ✅ — data.go.kr 키와 별개
- **갱신:** 일 단위(공고 등록 시)

### 요청 파라미터 ⚠️

| 파라미터 | 설명 |
|---|---|
| `crtfcKey` | 인증키 |
| `dataType` | `json` / `xml` |
| `searchCnt` | 조회 건수 |
| `pageUnit` / `pageIndex` | 페이지 크기 / 번호 |
| `searchLclasId` | 분야 대분류 코드(선택) |
| `hashtags` | 키워드(선택) |

### 분야 대분류 (`pldirSportRealmLclasCodeNm`) ⚠️
금융 · 기술 · 인력 · 수출 · 내수(판로) · 창업 · 경영 · 기타

### 주요 응답 필드 ⚠️

| 필드 | 의미 | → 통합 |
|---|---|---|
| `pblancId` | 공고 ID | `source_uid` |
| `pblancNm` | 사업명 | `title` |
| `jrsdInsttNm` | 소관기관 | `agency` |
| `excInsttNm` | 수행기관 | `agency`(보조) |
| `reqstBeginEndDe` | 신청기간(시작~종료) | `deadline`(종료 파싱) |
| `creatPnttm` | 등록일시 | `posted_at` |
| `pldirSportRealmLclasCodeNm` | 분야 | `category` |
| `pblancUrl` | 상세 URL | `detail_url` |

### 증분 전략 & 한계
`creatPnttm`(등록일) 역순으로 이미 본 `pblancId` 만날 때까지. **예산·필수자격·평가항목은 미제공** → `pblancUrl` 상세 본문 추가 수집 + LLM 추출. 입찰·R&D 과제는 미포함(각각 §1, §4 담당).

---

## 3. K-Startup 사업공고 조회

- **출처:** data.go.kr `15125364`(K-Startup 조회서비스) ✅ + K-Startup 자체 OpenAPI(`nidview.k-startup.go.kr`) ✅
- **인증:** data.go.kr 키 · **갱신:** 일 단위
- **관련 데이터셋:** `15112711`(창업지원공고), `15125366`(주관기관 정보)

### 오퍼레이션
- `getAnnouncementInformation` (지원사업 공고정보) ✅
- `getBusinessInformation` (통합공고 지원사업 정보)
- `getContentInformation` (콘텐츠)

> data.go.kr 신규형 호출 패턴(예): `https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01` ⚠️ — 서비스 경로/버전 suffix는 명세에서 재확인.

### 요청 파라미터 ⚠️
`serviceKey`, `page`, `perPage`, `returnType`(json/xml) + 조건 필터: 통합공고여부 · 사업공고명 · 지원사업분류 · 공고접수시작/종료일시(`YYYYMMDD`) · 지원지역 · 신청대상 · 모집진행여부 ✅(검색조건 확인)

### 주요 응답 필드 ⚠️

| 필드 | 의미 | → 통합 |
|---|---|---|
| (공고 식별자) | 공고 일련번호 | `source_uid` |
| `biz_pbanc_nm` | 사업공고명 | `title` |
| `pbanc_ntrp_nm` | 공고기관명 | `agency` |
| `supt_biz_clsfc` | 지원사업분류 | `category` |
| `pbanc_rcpt_bgng_dt` | 접수 시작일 | `posted_at` |
| `pbanc_rcpt_end_dt` | 접수 종료일 | `deadline` |
| `aply_trgt` / `supt_regin` | 신청대상 / 지원지역 | 메타 |
| `detl_pg_url` | 상세 URL | `detail_url` |

### 증분 전략
`pbanc_rcpt_bgng_dt` 또는 등록일 역순 수집. `rcrt_prgs_yn`(모집진행)으로 마감건 필터 가능. 기업마당과 창업분야 **중복 가능** → `(source, source_uid)` 분리 보관 후 표시단계 dedup.

---

## 4. NTIS 국가R&D통합공고

- **출처:** NTIS OpenAPI(`https://www.ntis.go.kr/rndopen/api/mng/apiMain.do`) ✅ / 공고검색 `ThSearchResultAnnouncementList.do` ✅
- **인증:** ⚠️ **NTIS 자체 R&D데이터신청** 키가 필요할 수 있음(data.go.kr `15077315`은 *과제검색*으로 공고와 별개) — **활용 가능 API 형태 확인 필요**
- **갱신:** 수시(공고 등록 시)

### 주요 항목(공고) ⚠️

| 항목 | 의미 | → 통합 |
|---|---|---|
| 공고일련번호 | 식별자 | `source_uid` |
| 공고명 | | `title` |
| 부처명 / 전문기관 | 발주 | `agency` |
| 공고일자 | | `posted_at` |
| 접수기간(시작~종료) | | `deadline` |
| 공고유형(신규/계속) | | 메타 |
| 공고 URL | | `detail_url` |

### 증분 전략 & 대안
공고일자 기준 증분. **NTIS 공고용 Open API 제공형태가 불확실**하므로 구현 시 (a) NTIS OpenAPI 신청 → API, (b) 불가 시 `ThSearchResultAnnouncementList` 파싱(Tier B) 중 택1. IRIS(`iris.go.kr`)는 접수 포털로 상보 활용.

---

## 5. 통합 매핑 요약

> ⚠️ **매핑 정본은 [db-schema §6](db-schema-opportunities.md)이다.** 아래 표는 개요용이며, 이후 스키마 결정으로 갱신된 부분이 있다: ① 나라장터 `source_uid = bidNtceNo`(차수 미포함, 차수는 `source_ord`) — 아래/§1의 `bidNtceNo+bidNtceOrd`는 **구버전 표기**. ② K-Startup `pbanc_rcpt_bgng_dt`는 `posted_at`이 아니라 `application_start_at`. 충돌 시 db-schema를 따른다.

| 통합 필드 | 나라장터 | 기업마당 | K-Startup | NTIS |
|---|---|---|---|---|
| `source` | `narajangter` | `bizinfo` | `kstartup` | `ntis` |
| `source_uid` | `bidNtceNo`+`bidNtceOrd` | `pblancId` | 공고일련번호 | 공고일련번호 |
| `title` | `bidNtceNm` | `pblancNm` | `biz_pbanc_nm` | 공고명 |
| `agency` | `ntceInsttNm`/`dminsttNm` | `jrsdInsttNm`/`excInsttNm` | `pbanc_ntrp_nm` | 부처/전문기관 |
| `budget` | `presmptPrce`/`asignBdgtAmt` | (상세추출) | (상세추출) | (상세추출) |
| `deadline` | `bidClseDt` | `reqstBeginEndDe` | `pbanc_rcpt_end_dt` | 접수종료 |
| `posted_at` | `bidNtceDt` | `creatPnttm` | `pbanc_rcpt_bgng_dt` | 공고일자 |
| `detail_url` | `bidNtceDtlUrl` | `pblancUrl` | `detl_pg_url` | 공고 URL |
| `raw_json` | 원본 보존 | 원본 보존 | 원본 보존 | 원본 보존 |

---

## 6. 권장 구현 순서

1. **나라장터** (✅ 정식 API·실시간·필드 풍부) — 가장 안정적, 첫 수집기로 파이프라인(증분→정규화→UPSERT→임베딩) 검증.
2. **기업마당** (✅ 단일 키·집계 범위 넓음) — 정부지원사업 커버, 상세 추출 파이프 추가.
3. **K-Startup** (✅ 창업분야 보강) — 기업마당과 dedup 정책 확정.
4. **NTIS** (⚠️ 인증/형태 확인 필요) — API 가능여부 확인 후, 안 되면 파싱으로 차순위.

> 공통: §[data-ingestion.md](data-ingestion.md)의 증분·UPSERT·content_hash·스케줄(06:00) 설계를 그대로 적용.

---

## 부록 — 출처
- [조달청 나라장터 입찰공고정보서비스 (15129394)](https://www.data.go.kr/data/15129394/openapi.do)
- [나라장터 API 수집 예제(파라미터 참고)](https://gurumii.com/python/example-g2b-api-research-data)
- [기업마당 정책정보 개방 API 목록](https://www.bizinfo.go.kr/web/lay1/program/S1T175C174/apiList.do)
- [K-Startup 지원사업 공고정보 Open API](https://nidview.k-startup.go.kr/view/public/kisedKstartupService/announcementInformation)
- [창업진흥원 K-Startup 조회서비스 (15125364)](https://www.data.go.kr/data/15125364/openapi.do)
- [NTIS OpenAPI](https://www.ntis.go.kr/rndopen/api/mng/apiMain.do)
- [NTIS 국가R&D통합공고 검색](https://www.ntis.go.kr/ThSearchResultAnnouncementList.do)
- [한국과학기술정보연구원 국가R&D 과제검색 서비스 (15077315)](https://www.data.go.kr/data/15077315/openapi.do)
