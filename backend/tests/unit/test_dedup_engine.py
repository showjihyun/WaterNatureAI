"""dedup 엔진(순수 함수) 단위 테스트 — display-dedup.md §1·§6 (보수적 병합).

핵심: 정규화 제목 완전 동일 + 기관/예산 호환 + 마감 ±3d 인 '진짜 중복'만 병합.
의미 유사/공구·차수 변형/다른 예산은 별개로 보존(과병합 회귀 방지).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from app.services.dedup.engine import (
    DedupOpp,
    cluster_opportunities,
    pick_canonical,
    should_merge,
    stable_group_id,
)

_DL = datetime(2026, 7, 7, tzinfo=timezone.utc)


def _opp(title, agency, *, source="narajangter", deadline=None, budget=None, desc=0):
    return DedupOpp(
        id=uuid.uuid4(),
        source=source,
        title=title,
        agency=agency,
        deadline=deadline,
        budget_amount=budget,
        posted_at=None,
        description_len=desc,
    )


def test_exact_duplicate_merges_across_sources():
    a = _opp("글로벌 AI 투자 기초데이터 구축 용역", "정보통신산업진흥원", deadline=_DL, budget=54_550_000)
    b = _opp("글로벌 AI 투자 기초데이터 구축 용역", "정보통신산업진흥원",
             source="kstartup", deadline=_DL, budget=54_550_000)
    clusters = cluster_opportunities([a, b])
    assert len(clusters) == 1 and len(clusters[0]) == 2


def test_whitespace_only_difference_merges():
    # 공백/대소문자 차이만 → 같은 공고로 병합.
    a = _opp("스마트도시  데이터 플랫폼 구축", "행정안전부", deadline=_DL, budget=100_000_000)
    b = _opp("스마트도시 데이터 플랫폼 구축", "행정안전부", deadline=_DL, budget=100_000_000)
    assert should_merge(a, b)


def test_lot_variants_not_merged():
    # 공구/차수 분할 발주(같은 프로그램, 다른 계약)는 별개로 보존 — 과병합 회귀 방지.
    a = _opp("OO지구 풀베기사업(이양1공구)", "지자체", deadline=_DL, budget=10_000_000)
    b = _opp("OO지구 풀베기사업(이양2공구)", "지자체", deadline=_DL, budget=10_000_000)
    assert not should_merge(a, b)
    assert len(cluster_opportunities([a, b])) == 2


def test_similar_topic_different_project_not_merged():
    # 같은 기관·마감·예산이라도 제목(=사업)이 다르면 병합 금지.
    a = _opp("사회복지 통합정보시스템 구축 용역", "보건복지부", deadline=_DL, budget=50_000_000)
    b = _opp("가스시설 안전관리 시스템 고도화 용역", "보건복지부", deadline=_DL, budget=50_000_000)
    assert not should_merge(a, b)


def test_different_budget_not_merged():
    # 제목·기관·마감 같아도 예산이 다르면 별개(다른 계약/차수).
    a = _opp("장비 구매", "기관", deadline=_DL, budget=100_000_000)
    b = _opp("장비 구매", "기관", deadline=_DL, budget=200_000_000)
    assert not should_merge(a, b)


def test_reregistration_with_new_deadline_merges_to_latest():
    # 같은 제목·기관·예산인데 마감만 다른 재공고(재등록) → 같은 공고로 병합, 대표=마감 늦은(활성) 건.
    a = _opp("연구장비 구매", "한국연구재단", deadline=_DL, budget=100_000_000)
    b = _opp("연구장비 구매", "한국연구재단", deadline=_DL + timedelta(days=11), budget=100_000_000)
    assert should_merge(a, b)
    assert len(cluster_opportunities([a, b])) == 1
    assert pick_canonical([a, b]) is b  # 마감 늦은 b가 대표


def test_pick_canonical_prefers_source_priority():
    a = _opp("X 용역", "어떤기관", source="ntis", deadline=_DL)
    b = _opp("X 용역", "어떤기관", source="narajangter", deadline=_DL)
    assert pick_canonical([a, b]).source == "narajangter"


def test_pick_canonical_prefers_filled_fields_on_same_source():
    a = _opp("Y 용역", "기관", deadline=None, budget=None)
    b = _opp("Y 용역", "기관", deadline=_DL, budget=10_000_000, desc=200)
    assert pick_canonical([a, b]) is b


def test_stable_group_id_is_order_independent():
    ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    assert stable_group_id(ids) == stable_group_id(list(reversed(ids)))
