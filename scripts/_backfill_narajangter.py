"""기존 narajangter open 공고 description/region 백필 + 재임베딩.

수집기 _build_description 풍부화(102필드 활용) 후, 이미 적재된 공고도 raw_json에서 재구성.
description 변경 → content_hash 변경 → 재임베딩 대상(embedded_hash != content_hash).
운영에선 재수집+embed 파이프라인이 점진 적용하지만, 즉시 반영 위해 일괄 처리.
"""
from __future__ import annotations

import time
from datetime import datetime, timezone

from sqlalchemy import or_, select

from app.core.config import settings
from app.db.base import SessionLocal
from app.db.models.opportunity import Opportunity
from app.services.collectors.narajangter import _build_description, _parse_region
from app.services.collectors.normalize import sha256_norm
from app.services.embedding import vectorstore
from app.services.embedding.provider import get_provider
from app.services.embedding.tasks import _embedding_text


def main() -> None:
    db = SessionLocal()
    opps = db.scalars(
        select(Opportunity).where(
            Opportunity.source == "narajangter", Opportunity.status == "open"
        )
    ).all()
    print(f"대상 open 공고: {len(opps)}", flush=True)

    desc_n = region_n = 0
    for o in opps:
        raw = o.raw_json or {}
        raw.setdefault("_category", o.category)
        nd = _build_description(raw)
        nr = _parse_region(raw)
        if nd != o.description:
            o.description = nd
            o.content_hash = sha256_norm(o.title, o.agency, o.deadline, o.budget_amount, nd)
            desc_n += 1
        if nr != o.region:
            o.region = nr
            if nr:
                region_n += 1
    db.commit()
    print(f"PHASE1 완료 — description 갱신 {desc_n} · region 설정 {region_n}", flush=True)

    # PHASE2 재임베딩 — content_hash 변경분 + 미임베딩분
    to_embed = db.scalars(
        select(Opportunity).where(
            Opportunity.source == "narajangter",
            Opportunity.status == "open",
            or_(
                Opportunity.embedded_hash.is_(None),
                Opportunity.embedded_hash != Opportunity.content_hash,
            ),
        )
    ).all()
    print(f"PHASE2 재임베딩 대상: {len(to_embed)}", flush=True)

    provider = get_provider()
    batch_size = 64
    t0 = time.time()
    for i in range(0, len(to_embed), batch_size):
        batch = to_embed[i : i + batch_size]
        vecs = provider.embed_batch([_embedding_text(o) for o in batch])
        for o, v in zip(batch, vecs):
            vectorstore.store_embedding(db, vectorstore.OPPORTUNITIES, str(o.id), v)
            o.embedded_hash = o.content_hash
            o.embedding_version = settings.embedding_version
            o.embedded_at = datetime.now(timezone.utc)
        db.commit()
        done = min(i + batch_size, len(to_embed))
        if (i // batch_size) % 5 == 0 or done == len(to_embed):
            print(f"  embedded {done}/{len(to_embed)} ({time.time() - t0:.0f}s)", flush=True)
    print(f"PHASE2 완료 — {len(to_embed)} 재임베딩 ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
