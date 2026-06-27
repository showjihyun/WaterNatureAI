# K-Startup · NTIS Collector 설계

> P0 잔여 2종. [BaseCollector](collector-base-bizinfo.md)를 확장한다.
> 관련: [P0 API 스펙 §3·§4](p0-source-spec.md) · [통합 스키마](db-schema-opportunities.md) · [수집·갱신 설계](data-ingestion.md)
> **작성 기준일:** 2026-06-18

---

## 1. K-Startup Collector

창업 지원사업 공고. data.go.kr `15125364`(또는 K-Startup 자체 OpenAPI).

### 1.1 특성
- **인증:** data.go.kr 키 · **페이징:** `page`/`perPage` · **포맷:** `returnType=json`
- **증분:** **서버 날짜필터 사용 가능** — `공고접수시작일시`/`종료일시`(`YYYYMMDD`)로 범위 조회 → 나라장터식 `[window.begin, window.end]` 폴링.
- **상세:** `detl_pg_url` 존재. 예산이 목록에 없으면 **부분 `requires_detail`**(예산만 보강) — MVP는 목록 필드로 시작, 예산 필요 시 enrich 추가.
- **중복:** 기업마당 창업분야와 겹침 → 분리 저장 + 표시단계 dedup([display-dedup.md](display-dedup.md)).

### 1.2 매핑

| 컬럼 | K-Startup 필드 |
|---|---|
| `source` | `'kstartup'` |
| `source_uid` | 공고 일련번호 |
| `title` | `biz_pbanc_nm` |
| `agency` | `pbanc_ntrp_nm` |
| `category` | `supt_biz_clsfc` |
| `application_start_at` | `pbanc_rcpt_bgng_dt` |
| `deadline` | `pbanc_rcpt_end_dt` |
| `posted_at` | (등록일, 없으면 NULL) |
| `region` | `supt_regin` |
| `detail_url` | `detl_pg_url` |
| `raw_json` | item |

### 1.3 의사코드

```python
class KStartupCollector(BaseCollector):
    source_code = "kstartup"
    requires_detail = False     # 예산 보강 필요 시 True로 + fetch_detail 구현

    def iter_pages(self, window):
        for page in count(1):
            items = client.fetch(service_key=KEY, return_type="json",
                                  page=page, per_page=100,
                                  rcpt_bgng=fmt_ymd(window.begin),  # 서버 날짜필터
                                  rcpt_end=fmt_ymd(window.end))
            if not items:
                return
            yield items
            if len(items) < 100 or page >= MAX_PAGES:
                return

    def parse_item(self, raw):
        return OpportunityDTO(
            source="kstartup", source_uid=raw["공고일련번호"],
            title=raw["biz_pbanc_nm"].strip(), agency=raw.get("pbanc_ntrp_nm"),
            category=raw.get("supt_biz_clsfc"), region=raw.get("supt_regin"),
            application_start_at=parse_kst(raw.get("pbanc_rcpt_bgng_dt")),
            deadline=parse_kst(raw.get("pbanc_rcpt_end_dt")),
            posted_at=parse_kst(raw.get("등록일")),
            detail_url=raw.get("detl_pg_url"),
            description=build_desc(raw), budget_raw=None, budget_amount=None,
            raw_json=raw, status=derive_status(parse_kst(raw.get("pbanc_rcpt_end_dt"))),
            content_hash=sha256_norm(title, agency, deadline, None, desc),
        )
```

---

## 2. NTIS Collector

국가R&D통합공고(R&D 과제). **API 제공 형태가 불확실** → 2경로 설계.

### 2.1 경로 — ✅ API 확정 ([spike](../05-spikes/blocker-resolution.md) §3)

**`data.go.kr 15074634` 과학기술정보통신부_사업공고** Open API 사용(별도 NTIS 키 불필요, **data.go.kr serviceKey**).

| 항목 | 값 |
|---|---|
| 엔드포인트 | `http://apis.data.go.kr/1721000/msitannouncementinfo/businessAnnouncMentList` |
| 파라미터 | `serviceKey`·`pageNo`·`numOfRows`·`returnType`(json/xml) |
| 갱신 | 매일 1회 · 트래픽 개발 10,000/일 |
| 응답 | 제목·상세URL·부처명·담당자·게시일·첨부 |

- **mode=api 확정(Tier A)**, 스크래핑(`ThSearchResultAnnouncementList`)은 후순위 폴백.
- ⚠️ **마감(`deadline`)·예산이 목록에 없을 수 있음** → 상세/첨부 보완 또는 NTIS 통합공고 추가 확인. `15074634`는 MSIT 중심 → IITP/NRF 세부 커버리지 점검.
- `15077315`(과제검색)은 공고 아님(별개).

### 2.2 매핑 (R&D 과제 특화)

| 컬럼 | NTIS 항목 |
|---|---|
| `source` | `'ntis'` |
| `source_uid` | 공고 일련번호 |
| `title` | 공고명 |
| `agency` | 부처명 / 전문기관 |
| `category` | 공고유형(신규/계속) |
| `posted_at` | 공고일자 |
| `deadline` | 접수종료 |
| `detail_url` | 공고 URL |

### 2.3 의사코드 (전략 패턴)

```python
class NtisCollector(BaseCollector):
    source_code = "ntis"
    requires_detail = False

    def __init__(self, mode):                 # 'api' | 'scrape'
        self.client = NtisApiClient() if mode == "api" else NtisScrapeClient()

    def iter_pages(self, window):
        for page in count(1):
            items = self.client.list(date_from=window.begin, date_to=window.end, page=page)
            if not items:
                return
            yield items
            if page >= MAX_PAGES:
                return

    def parse_item(self, raw):
        return OpportunityDTO(
            source="ntis", source_uid=raw["공고일련번호"], title=raw["공고명"].strip(),
            agency=raw.get("부처명") or raw.get("전문기관"),
            category=raw.get("공고유형"), posted_at=parse_kst(raw.get("공고일자")),
            deadline=parse_kst(raw.get("접수종료")), detail_url=raw.get("공고URL"),
            description=build_desc(raw), raw_json=raw,
            status=derive_status(parse_kst(raw.get("접수종료"))),
            content_hash=sha256_norm(title, agency, deadline, None, desc),
        )
```

- 스크래핑 경로는 [data-ingestion §6 준수사항](data-ingestion.md)(robots/지연/셀렉터 변경 감지) 적용.

---

## 3. 공통 엣지 케이스

| 케이스 | 처리 |
|---|---|
| K-Startup 등록일 부재 | `posted_at=NULL`, 증분은 접수시작 기준 |
| K-Startup ↔ 기업마당 중복 | 분리 저장 + 표시 dedup |
| NTIS API 불가 | mode=scrape 폴백, 알림 |
| NTIS 공고유형(계속/변경) | category·content_hash로 변경 추적 |
| 페이지 경계 | `<perPage` + `MAX_PAGES` 이중 종료 |
| 날짜/예산 파싱 실패 | 필드 NULL + 경고, 레코드 보존 |

---

## 4. 설정 (env)

```
KSTARTUP_SERVICE_KEY=...
KSTARTUP_BASE_URL=https://apis.data.go.kr/B552735/kisedKstartupService01
NTIS_MODE=api                 # api(기본, data.go.kr 15074634) | scrape(폴백)
NTIS_SERVICE_KEY=...          # data.go.kr serviceKey (별도 NTIS 키 불필요)
NTIS_BASE_URL=http://apis.data.go.kr/1721000/msitannouncementinfo
```

---

## 5. 테스트 & 다음 단계
- [ ] K-Startup 서버 날짜필터 파라미터명 최종 확정(명세/Swagger)
- [ ] K-Startup 응답 필드명(영문) 확정, 예산 보강 필요 여부 판단
- [ ] **NTIS 공고 OpenAPI 가용성 실검증** → mode 결정(api/scrape)
- [ ] NTIS scrape 셀렉터·IRIS 보완 범위 확정
- [ ] 4종 공통 BaseCollector 회귀 테스트(나라장터·기업마당·K-Startup·NTIS)
