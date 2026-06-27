# Alembic versions

스캐폴드는 **모델-퍼스트 autogenerate**를 사용한다:

```bash
alembic revision --autogenerate -m "0001 init"
alembic upgrade head
```

설계 문서의 논리적 마이그레이션 시퀀스(0001~0009)는
[`../../../docs/04-architecture/db-schema-opportunities.md`](../../../docs/04-architecture/db-schema-opportunities.md) §9.6 색인 참조.
autogenerate가 한 번에 생성하더라도, 운영 전 다음을 **수동 보강**해야 한다:

- `status` 일일 sweep 함수 `sweep_opportunity_status()` (0003) — DDL은 db-schema §9.2 (C)
- 부분 인덱스(`idx_opp_needs_embed`, `idx_opp_open_deadline`, `idx_cc_needs_embed`)
- `sources`·`plans` 시드 INSERT (0003 / 0008)
