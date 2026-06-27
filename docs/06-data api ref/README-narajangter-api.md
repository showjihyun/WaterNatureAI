# 나라장터(조달청) OpenAPI 통합 레퍼런스 — AI 작업용 SSOT

> **목적:** 다음 AI 툴/개발자가 **추가 조사 없이 바로** 나라장터 3종 수집기를 구현·실연결할 수 있도록 키·엔드포인트·오퍼레이션·필드 매핑을 한곳에 정리.
> **검증 상태:** 아래 3개 서비스 모두 **실 키로 live 호출하여 `resultCode=00` 확인**(2026-06-18). 필드명·날짜 포맷·totalCount 실측.
> **원본 명세:** 같은 폴더의 `조달청_OpenAPI참고자료_나라장터_{입찰공고정보서비스_1.2,낙찰정보서비스_1.1,공공데이터개방표준서비스_1.2}.docx`

---

## 0. 인증키 (data.go.kr)

- **계정:** 단일 data.go.kr 계정의 **하나의 serviceKey**로 아래 3개 서비스 모두 호출 가능(각각 활용신청 승인 필요).
- **키 저장 위치:** `backend/.env` 의 `NARAJANGTER_SERVICE_KEY` (Decoding 키). **이 문서에 평문 키를 넣지 않는다** — `.env`(또는 운영 Secret Manager)에서 읽는다.
- **Encoding vs Decoding:** 발급 시 두 가지가 나옴. 우리 클라이언트는 `httpx`가 쿼리스트링을 인코딩하므로 **Decoding 키**를 사용(Encoding 키를 쓰면 `%2B`,`%3D`가 이중 인코딩되어 인증 실패).
- **요청 제한:** 개발계정 1,000건/일(서비스별). 운영 전환 시 상향. 4유형×수페이지면 개발 한도로 충분.

```
# backend/.env
NARAJANGTER_SERVICE_KEY=<data.go.kr Decoding 키>
NARAJANGTER_BASE_URL=https://apis.data.go.kr/1230000/ad/BidPublicInfoService
NARAJANGTER_SCSBID_BASE_URL=https://apis.data.go.kr/1230000/as/ScsbidInfoService
NARAJANGTER_OPNSTD_BASE_URL=https://apis.data.go.kr/1230000/ao/PubDataOpnStdService
```

> ⚠️ **중요 정정(버그):** Base URL은 `/1230000/` 뒤에 **서비스 경로 prefix(`/ad`,`/as`,`/ao`)** 가 반드시 포함된다. 기존 코드/설계의 `https://apis.data.go.kr/1230000/BidPublicInfoService`(prefix 누락)는 **404** 가 난다. 아래 표의 정확한 base를 쓸 것.

---

## 1. 서비스 3종 요약 (live 검증)

| # | 서비스 | dataset | Base URL | 용도 | live total(샘플) |
|---|---|---|---|---|---|
| 1 | **입찰공고정보서비스** (BidPublicInfoService) | 15129394 | `https://apis.data.go.kr/1230000/ad/BidPublicInfoService` | 입찰공고 목록·상세·기초금액·변경이력 | 645(물품/1일) |
| 2 | **낙찰정보서비스** (ScsbidInfoService) | 15129397 | `https://apis.data.go.kr/1230000/as/ScsbidInfoService` | 개찰결과·낙찰업체·낙찰금액 | 267(물품/1일) |
| 3 | **공공데이터개방표준서비스** (PubDataOpnStdService) | 15058815 | `https://apis.data.go.kr/1230000/ao/PubDataOpnStdService` | 행안부 개방표준 형식의 공고/낙찰/계약 통합 | 2631(공고/1일) |

> 1↔3 관계: **필드명이 서로 다름**(3은 행안부 표준 스키마: 날짜 date/time 분리형). 1은 풍부한 원본 필드, 3은 표준화·낙찰/계약 통합 단일조회. P0 MVP는 **1(입찰공고)** 를 주 소스로, 2(낙찰)는 결과 보강, 3은 선택.

---

## 2. 공통 규약 (3개 서비스 동일)

- **HTTP:** GET. 응답 `type=json` 권장(xml도 가능).
- **Envelope (표준 data.go.kr):**
  ```json
  {"response":{
    "header":{"resultCode":"00","resultMsg":"정상 ..."},
    "body":{"items":[ {...}, ... ],"totalCount":645,"numOfRows":10,"pageNo":1}}}
  ```
  - 단건일 때 `items`가 `{"item":{...}}` 또는 `""`(NODATA)로 올 수 있어 방어 파싱 필요.
- **resultCode (표준):** `00` 정상 · `03` NODATA(빈 리스트 처리) · `01/02/04/05` 서버측 일시오류(재시도) · `10·11·12·20·21·22·30·31·32·33·99` 파라미터/인증/쿼터(비재시도). → `backend/app/services/collectors/client.py`에 구현됨.
- **요청 일시 포맷:** `inqryBgnDt`/`inqryEndDt` = **`YYYYMMDDHHMM`** 12자리 (예 `202506170000`~`202506172359`).
- **응답 일시 포맷:** 서비스 1·2는 **`yyyy-MM-dd HH:mm:ss`** (예 `2025-06-17 07:43:54`). 서비스 3은 **date/time 분리**(`bidClseDate`=`2017-01-06` + `bidClseTm`=`10:00`).
- **페이지네이션:** `pageNo`(1부터), `numOfRows`(최대 1000). 종료조건: `len(items)<numOfRows` 또는 `누적≥totalCount` 또는 `MAX_PAGES`.
- **공통 파라미터:** `serviceKey`, `type`, `numOfRows`, `pageNo` + 서비스별 `inqryDiv`/일시.

---

## 3. 서비스 1 — 입찰공고정보서비스 (BidPublicInfoService)

### 3.1 업무유형별 목록 오퍼레이션 (P0 수집 대상)
| 오퍼레이션 | 대상(category) |
|---|---|
| `getBidPblancListInfoThng` | 물품 |
| `getBidPblancListInfoServc` | 용역 |
| `getBidPblancListInfoCnstwk` | 공사 |
| `getBidPblancListInfoFrgcpt` | 외자 |

> 그 외 오퍼레이션(참고, 현재 미사용): `...PPSSrch`(검색조건판), `...BsisAmount`(기초금액), `getBidPblancListInfoChgHstry{Thng,Servc,Cnstwk}`(변경이력), `...LicenseLimit`(면허제한), `...PrtcptPsblRgn`(참가가능지역), `...Etc`(기타) 등.

### 3.2 요청 파라미터
| 파라미터 | 값/포맷 | 필수 | 설명 |
|---|---|---|---|
| `serviceKey` | Decoding 키 | ✓ | 인증 |
| `inqryDiv` | `1` | ✓ | 조회구분 1=입력일시(공고게시), 2=공고번호 기준 |
| `inqryBgnDt`/`inqryEndDt` | `YYYYMMDDHHMM` | ✓(div=1,3) | 조회 시작/종료 일시 |
| `pageNo`/`numOfRows` | int / ≤1000 | ✓ | 페이지/건수 |
| `type` | `json` | — | 응답 포맷 |
| `bidNtceNm`,`indstrytyCd` | str | — | (선택) 검색 필터 |

### 3.3 응답 필드 → opportunities 매핑 (검증 완료)
| opportunities 컬럼 | 나라장터 필드 | 비고 |
|---|---|---|
| `source` | — | 상수 `'narajangter'` |
| `source_uid` | `bidNtceNo` | 예 `R25BK00908293`. 차수 미포함 |
| `source_ord` | `bidNtceOrd` | 예 `000` → int 0 |
| `title` | `bidNtceNm` | |
| `agency` | `ntceInsttNm` ?? `dminsttNm` | 공고기관 우선 |
| `category` | (업무유형) | 물품/용역/공사/외자 |
| `budget_raw`/`budget_amount` | `presmptPrce` ?? `asignBdgtAmt` | 숫자 문자열(예 `4800000`) |
| `posted_at` | `bidNtceDt` | `yyyy-MM-dd HH:mm:ss` |
| `deadline` | `bidClseDt` | `yyyy-MM-dd HH:mm:ss` |
| `detail_url` | `bidNtceDtlUrl` | 신형 `g2b.go.kr/link/...` |
| `raw_json` | item 전체 | JSONB 보존 |

> 참고 추가 필드(미사용): `bidBeginDt`(입찰개시), `opengDt`(개찰), `rgstDt`(등록), `refNo`(참조번호), `bsnsDivNm`(업무구분명: 물품/용역/공사/외자).

### 3.4 검증된 샘플 (물품, 1일 윈도우)
```
resultCode=00, totalCount=645
bidNtceNo='R25BK00908293', bidNtceOrd='000'
bidNtceDt='2025-06-17 07:43:54', bidClseDt='2025-06-19 12:00:00'
presmptPrce='4800000', asignBdgtAmt='5280000'
bidNtceDtlUrl='https://www.g2b.go.kr/link/PNPE027_01/single/?bidPbancNo=R25BK00908293&bidPbancOrd=000'
```

---

## 4. 서비스 2 — 낙찰정보서비스 (ScsbidInfoService) [docx v1.1 확정]

### 4.1 업무유형별 목록 오퍼레이션 (핵심 4종 — "낙찰된 목록 현황")
| 오퍼레이션 | 대상(category) |
|---|---|
| `getScsbidListSttusThng` | 물품 |
| `getScsbidListSttusServc` | 용역 |
| `getScsbidListSttusCnstwk` | 공사 |
| `getScsbidListSttusFrgcpt` | 외자 |

> 전체 22종. 그 외: `getOpengResultListInfo{Thng,Servc,Cnstwk,Frgcpt}`(개찰결과·투찰자/순위/예가), `...Failing`(유찰), `...Rebid`(재입찰), `...OpengCompt`(개찰완료), `...PreparPcDetail`(복수예가 상세), `...PPSSrch`(조달청 검색판). 접미사: Thng=물품/Servc=용역/Cnstwk=공사/Frgcpt=외자.

### 4.2 요청 파라미터
| 파라미터 | 값/포맷 | 설명 |
|---|---|---|
| `serviceKey`,`type`,`pageNo`,`numOfRows` | — | 공통 |
| `inqryDiv` | `1`~`4` | **1=등록일시 / 2=공고일시 / 3=개찰일시 / 4=공고번호 단건** |
| `inqryBgnDt`/`inqryEndDt` | `YYYYMMDDHHMM` | inqryDiv 1·2·3일 때 필수. inqryDiv가 가리키는 일시에 적용 |
| `bidNtceNo` | str | inqryDiv=4일 때 필수 |

> **증분 권장: `inqryDiv=1`(등록일시)** — 낙찰/개찰 정보가 시스템에 등록·갱신되는 시점이라 누락 최소. 개찰일시 기준이 필요하면 `inqryDiv=3`.

### 4.3 응답 필드 (docx + live 검증)
| 필드 | 의미 | 샘플 |
|---|---|---|
| `bidNtceNo`/`bidNtceOrd` | 공고번호/차수 | R25BK00965123 / 000 |
| `bidClsfcNo`/`rbidNo` | 입찰분류번호/재입찰번호 | 1 / 000 |
| `bidNtceNm` | 공고명(사업명) | |
| `prtcptCnum` | 참가업체수 | 2 |
| **`bidwinnrNm`** | **최종낙찰업체명** | 주식회사 동광보일러 |
| **`bidwinnrBizno`** | **낙찰업체 사업자번호** | 1408121883 |
| `bidwinnrCeoNm`/`bidwinnrAdrs`/`bidwinnrTelNo` | 대표/주소/전화(휴대폰 `*`마스킹) | |
| **`sucsfbidAmt`** | **최종낙찰금액(원)** | 83500000 |
| **`sucsfbidRate`** | **최종낙찰률(%)** | 97.82 |
| `rlOpengDt` | 실개찰일시 | `2025-07-23 11:00:00` |
| `dminsttCd`/`dminsttNm` | 수요기관 | 인천광역시 종합건설본부 |
| `rgstDt` | 등록일시 | `2025-07-23 15:20:05` |
| `fnlSucsfDate` | 최종낙찰일자 | `2025-07-23` (날짜만) |

> ⚠️ 낙찰금액/업체 필드는 `sucsfbidAmt`/`bidwinnrNm`/`bidwinnrBizno` (코드에서 후보로 거론된 `scsbidAmt`/`scsbidCorpNm` 아님). 개찰결과(getOpengResultListInfo*)는 추가로 `opengDt`,`opengRank`(순위),`prcbdrNm`/`bidprcAmt`(투찰업체/금액),`bidprcrt`(투찰률) 등 제공.
- **활용:** 입찰공고와 `bidNtceNo`+`bidNtceOrd`로 조인 → 낙찰 결과 보강. opportunities 본 테이블이 아니라 **별도 `opportunity_awards` 테이블** 권장(스키마 §6 TODO).
- 응답 일시 = `yyyy-MM-dd HH:mm:ss`. 샘플: `resultCode=00, totalCount=267`(물품/1일).

---

## 5. 서비스 3 — 공공데이터개방표준서비스 (PubDataOpnStdService) [docx v1.2 확정]

### 5.1 오퍼레이션 (3개 — 도메인별 1개씩)
| 오퍼레이션 | 데이터 | live totalCount |
|---|---|---|
| `getDataSetOpnStdBidPblancInfo` | 입찰공고(표준형) | 2631 (1일) |
| `getDataSetOpnStdScsbidInfo` | 낙찰/개찰(표준형) | 315130 |
| `getDataSetOpnStdCntrctInfo` | 계약(표준형) | 8302 |

### 5.2 요청 파라미터 — ⚠️ `inqryDiv` 없음, 도메인별 기준일시 분리
| 오퍼레이션 | 기간 파라미터 | 포맷 | 추가 |
|---|---|---|---|
| BidPblancInfo | `bidNtceBgnDt`/`bidNtceEndDt` | `YYYYMMDDHHMM` | — |
| ScsbidInfo | `opengBgnDt`/`opengEndDt` | `YYYYMMDDHHMM` | `bsnsDivCd`(업무구분코드) |
| CntrctInfo | `cntrctCnclsBgnDate`/`cntrctCnclsEndDate` | (Date형, `…Date` 접미사) | — |
- 공통: `serviceKey`,`type`,`pageNo`,`numOfRows`. (입찰공고/낙찰서비스의 `inqryDiv`/`inqryBgnDt`는 여기 **없음**.)

### 5.3 응답 필드 — **날짜 전부 date+time 분리형** (서비스1·2와 필드명 다름)
- **공고**(getDataSetOpnStdBidPblancInfo): `bidNtceNo`,`bidNtceOrd`,`bidNtceNm`,`bidNtceSttusNm`, `bidNtceDate`+`bidNtceBgn`(공고일+시각), `bidBeginDate`+`bidBeginTm`, `bidClseDate`+`bidClseTm`, `bidPrtcptQlfctRgstClseDate`+`…Tm`, `opengDate`+`opengTm`, `ntceInsttNm`/`Cd`, `dmndInsttNm`/`Cd`(수요기관), `asignBdgtAmt`, `presmptPrce`, `bsnsDivNm`, `bidNtceUrl`, `dataBssDate`.
- **낙찰**(getDataSetOpnStdScsbidInfo): `bidNtceNo`,`bsnsDivNm`,`presmptPrce`,`bssAmt`(기초금액),`rsrvtnPrce`(예정가),`opengDate`+`opengTm`,`opengRank`,`bidprcCorpNm`/`Bizrno`(투찰업체),`bidprcAmt`,`bidprcRt`,`sucsfYn`,`fnlSucsfAmt`/`Rt`,`fnlSucsfDate`,`fnlSucsfCorpNm`/`Bizrno`/`Adrs`/`ContactTel`,`sucsfLwstlmtRt`(낙찰하한율).
- **계약**(getDataSetOpnStdCntrctInfo): `cntrctNo`,`untyCntrctNo`,`cntrctOrd`,`cntrctNm`,`bsnsDivNm`,`cntrctCnclsDate`,`cntrctPrd`(계약기간 `yyyy.MM.dd.`),`cntrctAmt`,`ttalCntrctAmt`,`bidNtceNo`,`cntrctInsttNm`(계약기관),`dmndInsttNm`,`rprsntCorpNm`/`Bizrno`(대표업체),`prvtcntrctRsn`(수의계약사유),`bidNtceUrl`.

> **핵심 차이(정규화 영향):** 날짜 = `yyyy-MM-dd` + 시각 = `HH:mm`(초 없음, **분리 필드**). 정규화 시 `bidClseDate`+`bidClseTm`을 합쳐 `parse_kst("2025-07-08 15:00")` 호출. URL은 `bidNtceUrl`(서비스1=`bidNtceDtlUrl`). 수요기관 `dmndInsttNm`(서비스1=`dminsttNm`). 샘플: `bidClseDate`=`2025-07-08`,`bidClseTm`=`15:00`.

> **서비스1 vs 3 관계(서브에이전트 판단):** 대체 아님 / **용도 분담**. 공고 실시간·풍부한 필드 = 서비스1(BidPublicInfoService). 공고+낙찰+계약을 표준 단일포맷으로 일괄 적재 = 서비스3. **P0 MVP는 서비스1로 충분** — 서비스3은 낙찰/계약 통합 적재가 필요할 때 채택.

---

## 6. 수집 스케줄 & 백엔드 구조 (매일 AM 09:00 KST INSERT) — [1단계 적용 완료]

- **스케줄(적용됨):** `app/core/celery_app.py`에 `collectors.run_all` = KST **09:00**. env `COLLECT_SCHEDULE_HOUR/MINUTE`로 조정. 파이프라인 상대순서 보존(sweep 08:50 → 수집 09:00 → dedup 09:30 → 매칭 10:00 → 브리핑 11:00). celery `timezone=Asia/Seoul`.
- **증분 윈도우:** `[last_success_at - INGEST_BUFFER_DAYS, now]` (KST). 최초 `INGEST_BACKFILL_DAYS`(90일).
- **멱등:** `(source, source_uid)` UPSERT + `content_hash` 변경감지. 동일 윈도우 재실행 무해.
- **소스 코드 분리:** opportunities/source_ingestion_state의 `source` 값
  - 입찰공고 → `'narajangter'`
  - 낙찰 → (결과 보강 테이블, opportunities 직접 INSERT 아님 권장)
  - 표준개방 → 선택(`'narajangter_std'` 등으로 분리하거나 미사용)
- 관련 코드: `backend/app/services/collectors/{client,base,narajangter,registry,tasks}.py`, `backend/app/core/celery_app.py`(Beat 스케줄).

---

## 7. 빠른 시작 (다음 AI 툴/개발자용)

```bash
# 1) 인프라 기동
cd backend && docker compose -f docker-compose.dev.yml up -d postgres redis

# 2) 키 확인 (backend/.env 의 NARAJANGTER_SERVICE_KEY)

# 3) live 스모크 (입찰공고 물품)
python - <<'PY'
import httpx, os
from app.core.config import settings
url = settings.narajangter_base_url + "/getBidPblancListInfoThng"
r = httpx.get(url, params={"serviceKey":settings.narajangter_service_key,"type":"json",
  "inqryDiv":1,"inqryBgnDt":"202506170000","inqryEndDt":"202506172359","pageNo":1,"numOfRows":3}, timeout=30)
print(r.json()["response"]["header"])
PY

# 4) 테스트
python -m pytest tests/unit -q
TEST_DATABASE_URL="postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar_test" \
  python -m pytest tests/integration -q
```

---

## 8. 진행 단계
**1단계 [완료]** — 입찰공고 URL 정정 + KST 09:00 스케줄
- [x] base URL prefix(`/ad`,`/as`,`/ao`) 정정 (config + .env + .env.example).
- [x] Celery Beat 수집 09:00 배선(config 기반, 파이프라인 상대순서 보존).
- [x] 입찰공고 4유형 live 검증(resultCode=00) + 실 Postgres E2E 수집.

**2단계 [예정]** — 낙찰(ScsbidInfoService) 수집
- [ ] `opportunity_awards` 테이블 + 마이그레이션(공고 `bidNtceNo`+`bidNtceOrd` 조인, 낙찰업체/금액/낙찰률).
- [ ] `ScsbidCollector`(getScsbidListSttus* 4유형, inqryDiv=1 등록일시 증분) + registry 등록 + 09:00 체인 합류.

**보류** — 표준서비스(3): 서비스1과 중복 → MVP 미채택. 계약 데이터 필요 시 재검토.
