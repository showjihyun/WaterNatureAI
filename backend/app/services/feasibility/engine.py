"""수행 가능성(Go/No-Go) 판단 엔진 — 규칙 기반, LLM 미사용.

회사 역량(tech_level, max_project_budget, capable_categories)과
공고 데이터(budget_amount, category)를 대조해 verdict(go/review/no_go)와 근거를 반환.

역량 미설정 가드: max_project_budget(None/<=0) AND not capable_categories → None 반환.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# 감당 규모의 N배까지는 '검토 필요', 초과는 '수행 어려움'
REVIEW_RATIO = 1.5


def _fmt_amount(amount: int) -> str:
    """금액을 억/만원 단위로 간결하게 포맷."""
    if amount >= 100_000_000:
        ok = amount / 100_000_000
        # 딱 떨어지면 정수, 아니면 소수 1자리
        if ok == int(ok):
            return f"{int(ok)}억원"
        return f"{ok:.1f}억원"
    if amount >= 10_000:
        man = amount // 10_000
        return f"{man}만원"
    return f"{amount:,}원"


@dataclass
class FeasibilityResult:
    verdict: str          # "go" | "review" | "no_go"
    label: str            # "수행 가능" | "검토 필요" | "수행 어려움"
    reasons: list[str] = field(default_factory=list)


_VERDICT_LABEL: dict[str, str] = {
    "go": "수행 가능",
    "review": "검토 필요",
    "no_go": "수행 어려움",
}


def assess_feasibility(
    *,
    tech_level: int | None,
    max_project_budget: int | None,
    capable_categories: list[str] | None,
    budget_amount: int | None,
    category: str | None,
) -> FeasibilityResult | None:
    """역량과 공고를 대조해 수행 가능성을 반환.

    역량이 전혀 설정되지 않은 경우(판단 불가) → None.
    """
    # ── 역량 미설정 가드 ───────────────────────────────────────────────────
    budget_cap_set = max_project_budget is not None and max_project_budget > 0
    cats_set = bool(capable_categories)
    if not budget_cap_set and not cats_set:
        return None

    # 차원별 플래그(flag: 'ok'|'review'|'no') 및 근거 수집
    flags: list[str] = []
    reasons: list[str] = []

    # ── 유형 판단 ─────────────────────────────────────────────────────────
    if cats_set:
        if category and category in capable_categories:  # type: ignore[operator]
            flags.append("ok")
            reasons.append(f"{category} 수행 가능")
        elif category:
            flags.append("no")
            reasons.append(f"{category} 유형 미수행")
        # category 없으면 유형 판단 생략

    # ── 규모 판단 ─────────────────────────────────────────────────────────
    size_flag: str | None = None
    if budget_cap_set:
        cap: int = max_project_budget  # type: ignore[assignment]
        if budget_amount is None:
            size_flag = "review"
            flags.append("review")
            reasons.append("예산 미공개, 규모 확인 필요")
        elif budget_amount <= cap:
            size_flag = "ok"
            flags.append("ok")
            reasons.append(f"사업규모 적정(예산 ≤ 감당 {_fmt_amount(cap)})")
        elif budget_amount <= cap * REVIEW_RATIO:
            ratio = budget_amount / cap
            size_flag = "review"
            flags.append("review")
            reasons.append(f"규모 부담(예산이 감당의 {ratio:.1f}배)")
        else:
            size_flag = "no"
            flags.append("no")
            reasons.append(
                f"규모 초과(예산 {_fmt_amount(budget_amount)} > 감당 {_fmt_amount(cap)})"
            )

    # ── 기술수준 보조 근거 ────────────────────────────────────────────────
    if tech_level is not None and tech_level <= 2 and size_flag in ("no", "review"):
        reasons.append("기술수준 대비 난이도 높을 수 있음")

    # ── verdict 결정(worst-of) ────────────────────────────────────────────
    if "no" in flags:
        verdict = "no_go"
    elif "review" in flags:
        verdict = "review"
    else:
        verdict = "go"

    return FeasibilityResult(
        verdict=verdict,
        label=_VERDICT_LABEL[verdict],
        reasons=reasons[:4],  # 최대 4개
    )
