"""단위 테스트: assess_feasibility 규칙 검증 (LLM 미사용, DB 불필요)."""
from __future__ import annotations

from app.services.feasibility.engine import REVIEW_RATIO, assess_feasibility


# ── 역량 미설정 가드 ──────────────────────────────────────────────────────────

def test_no_capability_returns_none():
    """max_project_budget 없고 capable_categories 없으면 None."""
    result = assess_feasibility(
        tech_level=3, max_project_budget=None, capable_categories=None,
        budget_amount=500_000_000, category="용역",
    )
    assert result is None


def test_budget_zero_and_no_categories_returns_none():
    """max_project_budget=0 도 미설정으로 간주."""
    result = assess_feasibility(
        tech_level=None, max_project_budget=0, capable_categories=None,
        budget_amount=100_000_000, category="물품",
    )
    assert result is None


def test_only_categories_set_no_budget_not_none():
    """categories만 설정돼도 판단 가능(None 아님)."""
    result = assess_feasibility(
        tech_level=None, max_project_budget=None, capable_categories=["용역"],
        budget_amount=None, category="용역",
    )
    assert result is not None


# ── 유형 판단 ─────────────────────────────────────────────────────────────────

def test_category_not_in_capable_is_no_go():
    """수행 불가 유형이면 no_go."""
    result = assess_feasibility(
        tech_level=3, max_project_budget=None, capable_categories=["물품", "용역"],
        budget_amount=None, category="공사",
    )
    assert result is not None
    assert result.verdict == "no_go"
    assert any("공사" in r for r in result.reasons)


def test_category_in_capable_ok():
    """수행 가능 유형 + 예산 없으면 review(예산 미공개)."""
    result = assess_feasibility(
        tech_level=3, max_project_budget=500_000_000, capable_categories=["용역"],
        budget_amount=None, category="용역",
    )
    assert result is not None
    assert result.verdict == "review"
    assert any("용역 수행 가능" in r for r in result.reasons)


def test_category_none_skips_type_check():
    """공고에 category 없으면 유형 판단 생략 — 규모만으로 판단."""
    result = assess_feasibility(
        tech_level=None, max_project_budget=1_000_000_000, capable_categories=["물품"],
        budget_amount=500_000_000, category=None,
    )
    assert result is not None
    assert result.verdict == "go"


# ── 규모 판단 ─────────────────────────────────────────────────────────────────

def test_budget_within_cap_is_go():
    """예산 <= 감당 규모 → go."""
    cap = 1_000_000_000
    result = assess_feasibility(
        tech_level=None, max_project_budget=cap, capable_categories=None,
        budget_amount=800_000_000, category=None,
    )
    assert result is not None
    assert result.verdict == "go"
    assert any("적정" in r for r in result.reasons)


def test_budget_equal_cap_is_go():
    """예산 == 감당 규모 정확히 → go."""
    cap = 500_000_000
    result = assess_feasibility(
        tech_level=None, max_project_budget=cap, capable_categories=None,
        budget_amount=cap, category=None,
    )
    assert result is not None
    assert result.verdict == "go"


def test_budget_1_2x_cap_is_review():
    """예산이 감당의 1.2배 → review(REVIEW_RATIO=1.5 이내)."""
    cap = 1_000_000_000
    budget = int(cap * 1.2)
    result = assess_feasibility(
        tech_level=None, max_project_budget=cap, capable_categories=None,
        budget_amount=budget, category=None,
    )
    assert result is not None
    assert result.verdict == "review"
    assert any("부담" in r for r in result.reasons)


def test_budget_exactly_review_ratio_is_review():
    """예산 == cap * REVIEW_RATIO → review(경계값)."""
    cap = 1_000_000_000
    budget = int(cap * REVIEW_RATIO)
    result = assess_feasibility(
        tech_level=None, max_project_budget=cap, capable_categories=None,
        budget_amount=budget, category=None,
    )
    assert result is not None
    assert result.verdict == "review"


def test_budget_1_6x_cap_is_no_go():
    """예산이 감당의 1.6배 → no_go(REVIEW_RATIO 초과)."""
    cap = 1_000_000_000
    budget = int(cap * 1.6)
    result = assess_feasibility(
        tech_level=None, max_project_budget=cap, capable_categories=None,
        budget_amount=budget, category=None,
    )
    assert result is not None
    assert result.verdict == "no_go"
    assert any("초과" in r for r in result.reasons)


def test_budget_none_with_cap_is_review():
    """예산 미공개(None) + 감당 규모 설정 → review."""
    result = assess_feasibility(
        tech_level=None, max_project_budget=1_000_000_000, capable_categories=None,
        budget_amount=None, category=None,
    )
    assert result is not None
    assert result.verdict == "review"
    assert any("미공개" in r for r in result.reasons)


# ── 기술수준 보조 근거 ────────────────────────────────────────────────────────

def test_tech_level_low_adds_reason_on_size_review():
    """tech_level<=2 이고 규모 review → 기술수준 근거 추가."""
    cap = 1_000_000_000
    budget = int(cap * 1.2)
    result = assess_feasibility(
        tech_level=2, max_project_budget=cap, capable_categories=None,
        budget_amount=budget, category=None,
    )
    assert result is not None
    assert result.verdict == "review"
    assert any("기술수준" in r for r in result.reasons)


def test_tech_level_low_adds_reason_on_size_no():
    """tech_level<=2 이고 규모 no_go → 기술수준 근거 추가."""
    cap = 1_000_000_000
    budget = int(cap * 2.0)
    result = assess_feasibility(
        tech_level=1, max_project_budget=cap, capable_categories=None,
        budget_amount=budget, category=None,
    )
    assert result is not None
    assert result.verdict == "no_go"
    assert any("기술수준" in r for r in result.reasons)


def test_tech_level_low_no_extra_reason_on_size_ok():
    """tech_level<=2 이지만 규모 ok → 기술수준 근거 없음."""
    cap = 1_000_000_000
    result = assess_feasibility(
        tech_level=2, max_project_budget=cap, capable_categories=None,
        budget_amount=500_000_000, category=None,
    )
    assert result is not None
    assert result.verdict == "go"
    assert not any("기술수준" in r for r in result.reasons)


def test_tech_level_high_no_extra_reason():
    """tech_level=3 이면 기술수준 근거 없음(규모 review여도)."""
    cap = 1_000_000_000
    budget = int(cap * 1.3)
    result = assess_feasibility(
        tech_level=3, max_project_budget=cap, capable_categories=None,
        budget_amount=budget, category=None,
    )
    assert result is not None
    assert not any("기술수준" in r for r in result.reasons)


# ── verdict 우선순위(worst-of) ────────────────────────────────────────────────

def test_verdict_worst_of_no_beats_review():
    """유형 no + 규모 review → no_go(worst-of)."""
    result = assess_feasibility(
        tech_level=None, max_project_budget=1_000_000_000, capable_categories=["물품"],
        budget_amount=int(1_000_000_000 * 1.2), category="공사",
    )
    assert result is not None
    assert result.verdict == "no_go"


def test_verdict_both_ok_is_go():
    """유형 ok + 규모 ok → go."""
    result = assess_feasibility(
        tech_level=4, max_project_budget=1_000_000_000, capable_categories=["용역"],
        budget_amount=500_000_000, category="용역",
    )
    assert result is not None
    assert result.verdict == "go"
    assert result.label == "수행 가능"


def test_verdict_labels_map_correctly():
    """label 매핑 검증."""
    # go
    r = assess_feasibility(
        tech_level=None, max_project_budget=1_000_000_000, capable_categories=None,
        budget_amount=100_000_000, category=None,
    )
    assert r is not None and r.label == "수행 가능"

    # no_go
    r2 = assess_feasibility(
        tech_level=None, max_project_budget=1_000_000_000, capable_categories=None,
        budget_amount=int(1_000_000_000 * 2.0), category=None,
    )
    assert r2 is not None and r2.label == "수행 어려움"


def test_reasons_capped_at_four():
    """reasons 최대 4개."""
    # tech_level low + 유형 ok + 규모 review: 3 reasons max here — just verify <= 4
    result = assess_feasibility(
        tech_level=2, max_project_budget=1_000_000_000, capable_categories=["용역"],
        budget_amount=int(1_000_000_000 * 1.3), category="용역",
    )
    assert result is not None
    assert len(result.reasons) <= 4
