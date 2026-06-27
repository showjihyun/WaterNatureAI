# embed_opportunity 워커 (pgvector) 설계

> 공고/기업 컨텍스트를 임베딩하여 **pgvector(각 행의 `embedding vector(1024)` 컬럼)**에 저장하는 워커. 수집기·Company Brain이 `content_hash` 변경 시 enqueue하고, 매칭 엔진의 후보 검색(retrieval)에 쓰인다.
>
> 🔧 **개정(2026-06-19): Qdrant → pgvector** (인프라 1개 감소, 검증 완료). 코드 정본 `app/services/embedding/vectorstore.py`(`store_embedding`/`get_embedding`/`search_opportunities`, 코사인). **이하 본문의 "Qdrant 컬렉션/upsert/point id" 언급은 pgvector(행 `embedding` 컬럼 / `vectorstore` / 행 PK)로 대체해 읽을 것.**
> 관련: [통합 스키마](db-schema-opportunities.md) · [BaseCollector/기업마당](collector-base-bizinfo.md) · [Matching 엔진](matching-engine.md) · [Architecture §6 Vector](architecture.md)
> 스택: Celery + Redis · **pgvector(Postgres)** · **작성 기준일:** 2026-06-18 (pgvector 개정 2026-06-19)

---

## 1. 역할 & 트리거

- **역할:** `opportunities`(및 `company_contexts`) 텍스트 → 임베딩 벡터 → 같은 행의 `embedding` 컬럼 저장(pgvector) + `embedded_hash/embedded_at` 갱신. 별도 벡터 DB 없음.
- **트리거:** 수집기/상세보강이 신규·변경분에 대해 `embed_opportunity.delay(id)` enqueue. (collector 설계의 재임베딩 enqueue 지점)
- **멱등:** 진입 시 `content_hash == embedded_hash` 이면 **스킵**. (중복 임베딩·비용 방지)

---

## 2. 임베딩 모델 선정

> ⚠️ **Anthropic Claude는 임베딩 API를 제공하지 않는다.** LLM(추천 근거 생성)은 최신 Claude를 쓰되([service-analysis §8](../00-overview/service-analysis.md)), **임베딩은 별도 모델**이 필요하다. 공고/기업 텍스트가 **한국어**이므로 다국어/한국어 성능이 관건.

| 후보 | 특징 | 비고 |
|---|---|---|
| **BGE-M3 (fastembed, OSS)** ✅ 채택 | 무료 OSS·**키 불필요**·ONNX 경량(torch 불필요)·다국어(한국어 포함)·**1024-dim(컬럼 일치)** | 최초 1회 모델 다운로드 |
| `dragonkue/bge-m3-ko` (sentence-transformers) | 한국어 특화(품질↑) | torch 의존(무거움) — 옵션, provider 교체로 1줄 |
| ~~Voyage AI~~ | 관리형·다국어 | **미사용**(외부 SDK·키 의존 — 사용자 결정 2026-06-20 제외) |
| OpenAI text-embedding-3-large | 다국어·고품질 | 차원 3072(비용↑) |
| ko-sroberta / KURE 등 | 한국어 특화 | 도메인 검증 필요 |

- **결정(2026-06-20):** MVP 기본 **BGE-M3 (fastembed, 무료 OSS·키 불필요·ONNX 경량, 1024-dim)** — voyage SDK 미사용(사용자 결정). 한국어 품질↑ 필요 시 `dragonkue/bge-m3-ko`(sentence-transformers)로 교체(provider 추상화로 1줄). 코드 `provider.py:BgeProvider`. 모델·차원은 설정값(`EMBEDDING_PROVIDER/MODEL/DIM`).
- 모델 교체 시 **차원이 바뀌면 `embedding` 컬럼 차원 변경 마이그레이션 + 전체 재임베딩** 필요 → `embedding_version` 으로 관리(§5). MVP는 `vector(1024)` 고정.

---

## 3. 임베딩 텍스트 구성

```
embedding_text =
  f"[{category}] {title}\n"
  f"발주/소관: {agency}\n"
  f"지역: {region}\n"
  f"{description}"
```
- `content_hash`(변경감지용, 좁은 필드)보다 **검색 품질을 위해 더 풍부하게** 구성.
- 길이 상한(모델 토큰 한도) 초과 시 `description` truncate.
- 빈 필드는 생략(라벨 노이즈 방지).

---

## 4. pgvector 저장 설계

벡터를 별도 DB가 아닌 **각 행의 `embedding vector(1024)` 컬럼**에 저장(같은 Postgres·한 트랜잭션).

| 테이블 | 벡터 컬럼 | 거리 | 필터(행 컬럼) |
|---|---|---|---|
| `opportunities` | `embedding vector(1024)` | Cosine `<=>`(`vector_cosine_ops`) | `status, deadline, source, category, region` |
| `company_contexts` | `embedding vector(1024)` | Cosine | `company_id, industry, region` |

- **행 PK가 곧 식별자** → `embedding` 컬럼 UPDATE = 자연 멱등(별도 point id 불필요).
- 메타데이터는 **행 컬럼 그대로** → 매칭 검색에서 SQL `WHERE status='open' AND deadline>now`로 필터.
- 인덱스: `opportunities`에 **hnsw (`vector_cosine_ops`)** = `idx_opp_embedding_hnsw`. `company_contexts`는 id 직접조회라 불필요.
- 코드: `app/services/embedding/vectorstore.py`(`store_embedding`/`get_embedding`/`search_opportunities`).

---

## 5. 모델/버전 관리

- payload·DB에 `embedding_version`(예: `voyage-ml-2:v1`) 기록.
- 전역 `EMBEDDING_VERSION` 설정과 다른 포인트 → **재임베딩 대상**.
- 모델/차원 변경 시: 새 컬렉션 생성(`opportunities_v2`) → 전체 백필 재임베딩 → 매칭 검색 대상 스위치 → 구 컬렉션 폐기(무중단 재인덱싱).

---

## 6. 워커 의사코드

```python
@celery.task(bind=True, autoretry_for=(TransientError,),
             retry_backoff=True, max_retries=5, rate_limit="...")
def embed_opportunity(self, opp_id):
    opp = opp_repo.get(opp_id)
    if opp is None:
        return
    # 멱등: 내용·모델버전 모두 최신이면 스킵
    if (opp.embedded_hash == opp.content_hash
            and opp.embedding_version == EMBEDDING_VERSION):
        return

    text = build_embedding_text(opp)
    vector = embedder.embed(text)            # Voyage/BGE 추상화, 재시도 내장

    # 같은 행의 embedding 컬럼에 저장(pgvector). 메타데이터는 행 컬럼이라 payload 불필요.
    vectorstore.store_embedding(db, "opportunities", str(opp.id), vector)
    opp_repo.set_embedded(opp_id, embedded_hash=opp.content_hash,
                          embedding_version=EMBEDDING_VERSION, embedded_at=now())
```

> `opportunities`에 `embedding_version TEXT` 컬럼 추가 권장(스키마 보강 항목). 부분 인덱스 `idx_opp_needs_embed`는 `embedded_hash IS DISTINCT FROM content_hash` 기준(버전 조건은 백필 쿼리에서 OR).

---

## 7. 배치 / 백필

```python
@celery.task
def embed_backfill(batch_size=128):
    # 재임베딩 대상: 해시 불일치 OR 버전 불일치
    ids = opp_repo.ids_needing_embed(EMBEDDING_VERSION, limit=batch_size)
    texts = [build_embedding_text(o) for o in ids]
    vectors = embedder.embed_batch(texts)        # 배치 호출(요금/지연 효율)
    qdrant.upsert("opportunities", points=[...])
    opp_repo.bulk_set_embedded(ids, EMBEDDING_VERSION)
    if more_remaining: embed_backfill.delay(batch_size)   # 청크 반복
```
- 증분(일일)은 단건 `embed_opportunity`, 최초/모델교체는 `embed_backfill` 배치.
- 임베딩 API **rate limit**·요금 고려해 배치 크기·동시성 조절.

---

## 8. 엣지 케이스

| 케이스 | 처리 |
|---|---|
| 임베딩 API 일시 오류 | 지수 백오프 재시도, 실패 시 다음 사이클 재시도(해시 미갱신) |
| 모델 차원 변경 | 새 컬렉션 + 전체 재임베딩(§5), 무중단 스위치 |
| 텍스트 토큰 초과 | description truncate |
| 삭제/만료 공고 | 추천 대상에서 status 필터로 제외(벡터는 잔존 가능, 주기적 정리 옵션) |
| 동시 enqueue 중복 | id 기반 upsert·멱등 스킵으로 무해 |
| `company_contexts` | 동일 워커 패턴(`embed_company_context`), point id=`company_contexts.id`, 추적 컬럼 동일(db-schema §10) |

---

## 9. 설정 (env)

```
EMBEDDING_PROVIDER=voyage            # voyage | bge | openai
EMBEDDING_MODEL=voyage-4             # 비용 우선: voyage-4-lite
EMBEDDING_DIM=1024                   # Matryoshka: 256~2048 (PoC에서 확정)
EMBEDDING_VERSION=voyage-4:v1
VOYAGE_API_KEY=                      # 없으면 임베딩 호출 시 RuntimeError(코드 검증됨)
EMBED_BATCH_SIZE=128
# 벡터 저장 = pgvector(DATABASE_URL의 Postgres). 별도 QDRANT_URL 없음.
```

---

## 10. 테스트 & 다음 단계
- [ ] `build_embedding_text` 스냅샷, 길이 초과 truncate
- [ ] 멱등: 동일 해시·버전 재호출 시 임베딩 호출 0회
- [x] pgvector `store_embedding`(행 UPDATE) + `<=>` 코사인 `search_opportunities` 왕복 검증 (완료)
- [ ] 모델버전 변경 시 재임베딩 대상 산출 쿼리
- [x] `opportunities.embedding_version` 컬럼 추가 → db-schema §10 `0004`
- [ ] 매칭 엔진의 retrieval이 이 컬렉션·payload 필터를 사용하도록 연결([matching-engine.md](matching-engine.md))
