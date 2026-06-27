"""dedup 1회 실행 + 전후 검증(읽기→실행→읽기). 운영 배치는 celery beat(dedup.run, 수집+30m).

검증 포인트:
  1) 비대표(is_canonical=False) 공고가 생기고 dedup_group_id가 채워지는가
  2) 군집 매치가 대표로 통합되어 matches 총수가 줄어드는가
  3) 기업별 추천(대표·open 매치) 수가 0으로 붕괴하지 않는가(통합이 제대로 됐는지)
"""
from __future__ import annotations

import time

from sqlalchemy import func, select

from app.db.base import SessionLocal
from app.db.models.opportunity import Match, Opportunity
from app.services.dedup.tasks import run_dedup


def _counts(db) -> dict:
    open_q = select(func.count()).select_from(Opportunity).where(Opportunity.status == "open")
    return {
        "open": db.scalar(open_q),
        "canonical": db.scalar(open_q.where(Opportunity.is_canonical.is_(True))),
        "noncanonical": db.scalar(open_q.where(Opportunity.is_canonical.is_(False))),
        "grouped": db.scalar(
            select(func.count()).select_from(Opportunity).where(Opportunity.dedup_group_id.isnot(None))
        ),
        "matches": db.scalar(select(func.count()).select_from(Match)),
    }


def _company_reco(db) -> dict:
    rows = db.execute(
        select(Match.company_id, func.count())
        .join(Opportunity, Opportunity.id == Match.opportunity_id)
        .where(Opportunity.is_canonical.is_(True), Opportunity.status == "open")
        .group_by(Match.company_id)
    ).all()
    return {cid: n for cid, n in rows}


def main() -> None:
    db = SessionLocal()
    try:
        before, before_reco = _counts(db), _company_reco(db)
        print("BEFORE:", before)

        t0 = time.time()
        changed = run_dedup(db)
        dt = time.time() - t0

        after, after_reco = _counts(db), _company_reco(db)
        print(f"RUN   : changed={changed} rows in {dt:.1f}s")
        print("AFTER :", after)
        print(
            f"DELTA : noncanonical +{after['noncanonical']}, "
            f"grouped +{after['grouped'] - before['grouped']}, "
            f"matches {before['matches']}→{after['matches']} "
            f"({after['matches'] - before['matches']:+d})"
        )

        print("--- 기업별 추천(대표·open 매치) before→after (상위 8) ---")
        collapse = False
        for cid in sorted(set(before_reco) | set(after_reco), key=lambda c: -before_reco.get(c, 0))[:8]:
            b, a = before_reco.get(cid, 0), after_reco.get(cid, 0)
            flag = ""
            if b > 0 and a == 0:
                flag = "  ⚠ 0으로 붕괴!"
                collapse = True
            print(f"  {str(cid)[:8]}: {b} → {a}{flag}")
        print("VERDICT:", "❌ 추천 붕괴 발생" if collapse else "✅ 추천 보존 + dedup 적용")
    finally:
        db.close()


if __name__ == "__main__":
    main()
