"""Matching 엔진 — 2단계(검색 prefilter + 하이브리드 스코어링).

정본: docs/04-architecture/matching-engine.md.
가중치: 기술30·실적25·고객20·산업15·지역10 (합 100).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

from sqlalchemy.orm import Session

from app.core.config import settings
from app.services.embedding import vectorstore
from app.services.keywords import INDUSTRY_KEYWORDS, STOPWORDS
from app.services.ksic import (
    KEYWORDS as KSIC_KEYWORDS,
    ETC as KSIC_ETC,
    keyword_in_text,
    ksic_name,
)

logger = logging.getLogger(__name__)

WEIGHTS = {"tech": 30, "track": 25, "customer": 20, "industry": 15, "region": 10}

# 임베딩 유사도 재스케일 상수 (e5 코사인 유사도 일반 대역 0.6~0.9 → 0~SIM_MAX)
SIM_FLOOR: float = 0.6
SIM_CEIL: float = 0.9
SIM_MAX: int = 15

# 한국 17개 시도 — 발주기관명에서 지역 파싱용
_SIDO_PATTERNS: list[tuple[str, str]] = [
    ("서울", "서울"),
    ("부산", "부산"),
    ("대구", "대구"),
    ("인천", "인천"),
    ("광주", "광주"),
    ("대전", "대전"),
    ("울산", "울산"),
    ("세종", "세종"),
    ("경기", "경기"),
    ("강원", "강원"),
    ("충북", "충북"),
    ("충남", "충남"),
    ("전북", "전북"),
    ("전남", "전남"),
    ("경북", "경북"),
    ("경남", "경남"),
    ("제주", "제주"),
]

# 발주기관 → 고객 세그먼트 매핑 (키워드 포함 여부로 판단)
_AGENCY_SEGMENTS: list[tuple[list[str], str]] = [
    (["국토교통부", "기획재정부", "과학기술정보통신부", "행정안전부", "국방부",
      "환경부", "산업통상자원부", "보건복지부", "문화체육관광부", "농림축산식품부",
      "해양수산부", "고용노동부", "여성가족부", "교육부", "외교부", "법무부",
      "중소벤처기업부"], "중앙행정기관"),
    (["시청", "군청", "구청", "도청", "특별시", "광역시", "특별자치시",
      "특별자치도", "시립", "군립", "구립"], "지자체"),
    (["공사", "공단", "공기업", "한국전력", "한국수자원", "한국도로", "LX",
      "LH", "SH", "GH", "코레일", "한전", "수자원공사", "도로공사"], "공기업"),
    (["교육청", "대학교", "대학", "초등학교", "중학교", "고등학교", "학교"], "교육기관"),
    (["국방", "육군", "해군", "공군", "병무청", "방위사업청"], "국방"),
    (["경찰", "소방", "검찰", "법원", "선거관리위원회"], "공공기관"),
]


# LLM 출력 스키마 (matching-engine.md §4)
_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "opportunity_id": {"type": "string"},
        "subscores": {
            "type": "object",
            "properties": {
                "tech":     {"type": "number"},
                "track":    {"type": "number"},
                "customer": {"type": "number"},
                "industry": {"type": "number"},
                "region":   {"type": "number"},
            },
        },
        "score": {"type": "number"},
        "reasons": {"type": "array", "items": {"type": "string"}},
        "risk": {"type": "string"},
    },
}


@dataclass
class ScoreResult:
    score: int
    reasons: list[str]
    subscore: dict[str, int]
    risk: str | None = None


# ── 내부 유틸 ────────────────────────────────────────────────────────────────

def _parse_region_from_agency(agency: str) -> str | None:
    """발주기관명에서 시도명 파싱. 매칭 실패 시 None."""
    for keyword, sido in _SIDO_PATTERNS:
        if keyword in agency:
            return sido
    return None


def _agency_to_segment(agency: str) -> list[str]:
    """발주기관명 → 해당되는 세그먼트 문자열 목록."""
    segments: list[str] = []
    for keywords, segment in _AGENCY_SEGMENTS:
        for kw in keywords:
            if kw in agency:
                segments.append(segment)
                break
    return segments


# ── 규칙 sub-score 헬퍼 (결정론, 키 불필요) ────────────────────────────────

def _region_score(ctx_regions: list[str], opp_region: str | None) -> int:
    """지역 일치 (0~10).

    - ctx.regions 비었거나 '전국' 포함 → 10 (지역 제약 없음)
    - opp_region 없음 → 10 (전국 공고 간주)
    - 정확 일치 → 10
    - 포함(substring) → 7
    - 불일치 → 0

    무회귀 보장: ctx.regions=[] 또는 ['전국'] 이면 opp_region 값 무관 10.
    """
    ctx_list = ctx_regions or []
    if not ctx_list or "전국" in ctx_list:
        return 10
    if not opp_region:
        return 10
    opp_r = opp_region.strip()
    for r in ctx_list:
        r = r.strip()
        if r == opp_r:
            return 10
        if r in opp_r or opp_r in r:
            return 7
    return 0


def _industry_score(
    ctx_industry: str | None,
    ctx_industries: list[str],
    opp_text: str,
    opp_category: str | None = None,
    opp_industry: str | None = None,
    ctx_capable_industries: list[str] | None = None,
) -> int:
    """산업(업종) 일치 (0~15).

    1. 표준 업종축(KSIC): opp.industry 가 회사 수행업종(capable_industries)에 포함 → 15.
       같은 분류축 직접 비교 = 가장 신뢰 높은 신호.
    2. 키워드 파생: 회사 산업(자유텍스트 INDUSTRY_KEYWORDS ∪ 회사 KSIC 업종 키워드)이
       opp_text 에 등장 → 15.
    3. 약한 매칭: 회사 산업명이 opp_text 부분 포함 → 8.
    4. 없으면 0.
    (구버전의 'opp.category(유형) vs 회사 산업' 비교 제거 — 유형은 업종축이 아니라 노이즈였음.)
    """
    caps = [c for c in (ctx_capable_industries or []) if c and c != KSIC_ETC]

    # 1. KSIC 표준 업종축 직접 매칭(최강 신호)
    if opp_industry and opp_industry != KSIC_ETC and opp_industry in caps:
        return 15

    if not opp_text:
        return 0

    all_industries: list[str] = []
    if ctx_industry:
        all_industries.append(ctx_industry.strip())
    all_industries.extend([i.strip() for i in (ctx_industries or []) if i.strip()])

    # 시그널 키워드 = 자유텍스트 산업 매핑 ∪ 회사 KSIC 업종 분류 키워드(분류 누락 보완)
    signal_keywords: set[str] = set()
    for ind in all_industries:
        signal_keywords.update(INDUSTRY_KEYWORDS.get(ind, [ind]))
    for code in caps:
        signal_keywords.update(KSIC_KEYWORDS.get(code, []))

    if not signal_keywords:
        return 0

    # 2. 강한 매칭: 시그널 키워드가 opp_text 에 하나라도 등장(부분문자열 오매칭 방지)
    for kw in signal_keywords:
        if keyword_in_text(kw, opp_text):
            return 15
    # 3. 약한 매칭: 회사 산업명이 opp_text 부분 포함
    for ind in all_industries:
        if keyword_in_text(ind, opp_text):
            return 8
    return 0


def _tech_keyword_score(
    ctx_technologies: list[str],
    ctx_keywords: list[str],
    opp_text: str,
) -> int:
    """기술 키워드 overlap (0~30).

    - ctx tech+keywords 합집합에서 STOPWORDS 제외 + 2자 이상만 남겨 변별 키워드 집합 구성.
    - opp_text 에서 distinct 매칭 개수 산정.
    - 희석 제거·uncap: min(30, matched * 12)  (1매칭=12, 2=24, 3+=30).
    - 변별 키워드 없거나 opp_text 없으면 0.
    """
    raw = {t.strip() for t in (ctx_technologies or []) + (ctx_keywords or []) if t.strip()}
    # 변별 키워드 = 2자 이상 + 불용어 제외
    discriminative = {t for t in raw if len(t) >= 2 and t not in STOPWORDS}
    if not discriminative or not opp_text:
        return 0
    opp_lower = opp_text.lower()
    matched = sum(1 for t in discriminative if t.lower() in opp_lower)
    return min(30, matched * 12)


def _customer_score(ctx_customers: list[str], opp_agency: str | None) -> int:
    """고객군 일치 (0~20).

    직접 매칭 (ctx.customers vs agency):
    - 정확 일치 → 20
    - 부분 포함 → 12

    세그먼트 매칭 (agency → 세그먼트 → ctx.customers):
    - ctx.customers 에 세그먼트명/agency 부분 포함 → 12

    fallback customers=[] → 0 (정직하게 0 유지).
    """
    if not opp_agency:
        return 0
    agency = opp_agency.strip()

    # 직접 매칭
    for c in ctx_customers or []:
        c = c.strip()
        if not c:
            continue
        if c == agency:
            return 20
        if c in agency or agency in c:
            return 12

    # 세그먼트 매칭
    segments = _agency_to_segment(agency)
    for seg in segments:
        for c in ctx_customers or []:
            c = c.strip()
            if not c:
                continue
            if c == seg or seg in c or c in seg:
                return 12

    return 0


def _resolve_effective_region(opportunity: dict) -> str | None:
    """opp.region → 없으면 agency 문자열에서 시도 파싱. 둘 다 없으면 None."""
    opp_region = opportunity.get("region")
    if opp_region:
        return opp_region
    agency = opportunity.get("agency") or ""
    return _parse_region_from_agency(agency) if agency else None


def _compute_rule_presets(company_context: dict, opportunity: dict) -> dict[str, int]:
    """결정론적 규칙 sub-score 계산. LLM 없이 실행 가능."""
    ctx = company_context
    opp = opportunity

    opp_text = " ".join(filter(None, [opp.get("title", ""), opp.get("description", "")]))

    # 지역: opp.region 없으면 agency 에서 파생
    effective_region = _resolve_effective_region(opp)

    region = _region_score(ctx.get("regions", []), effective_region)
    industry = _industry_score(
        ctx.get("industry"),
        ctx.get("industries", []),
        opp_text,
        opp.get("category"),
        opp.get("industry"),
        ctx.get("capable_industries", []),
    )
    tech = _tech_keyword_score(
        ctx.get("technologies", []),
        ctx.get("keywords", []),
        opp_text,
    )
    customer = _customer_score(
        ctx.get("customers", []),
        opp.get("agency"),
    )
    return {
        "region": region,
        "industry": industry,
        "tech": tech,
        "customer": customer,
    }


def _build_rule_reasons(
    company_context: dict, opportunity: dict, rule_scores: dict[str, int]
) -> list[str]:
    """LLM 없을 때 규칙 매칭 결과로 템플릿 근거 문장 생성."""
    reasons: list[str] = []

    # 기술 키워드 겹침 (변별 키워드 기준)
    raw = {
        t.strip()
        for t in (
            (company_context.get("technologies") or [])
            + (company_context.get("keywords") or [])
        )
        if t.strip()
    }
    discriminative = {t for t in raw if len(t) >= 2 and t not in STOPWORDS}
    opp_text = " ".join(
        filter(None, [opportunity.get("title", ""), opportunity.get("description", "")])
    )
    if discriminative and opp_text and rule_scores.get("tech", 0) > 0:
        matched_kw = [t for t in discriminative if t.lower() in opp_text.lower()]
        if matched_kw:
            reasons.append(f"기술 일치: {', '.join(sorted(matched_kw)[:5])}")

    # 지역 — effective_region 반영
    if rule_scores.get("region", 0) > 0:
        effective_region = _resolve_effective_region(opportunity)
        display_region = effective_region or "전국"
        reasons.append(f"지역 적합: {display_region}")

    # 산업(업종)
    if rule_scores.get("industry", 0) > 0:
        opp_ind = opportunity.get("industry")
        caps = [c for c in (company_context.get("capable_industries") or []) if c != KSIC_ETC]
        if opp_ind and opp_ind != KSIC_ETC and opp_ind in caps:
            # 표준 업종축 직접 일치 — 가장 명확한 근거.
            reasons.append(f"업종 적합: {ksic_name(opp_ind)} (표준 업종 일치)")
        else:
            industry = company_context.get("industry", "")
            # opp_text 에서 매칭된 산업 키워드 찾기
            matched_industry_kw = ""
            all_inds = []
            if industry:
                all_inds.append(industry)
            all_inds.extend(company_context.get("industries") or [])
            for ind in all_inds:
                kws = INDUSTRY_KEYWORDS.get(ind, [ind])
                for kw in kws:
                    if keyword_in_text(kw, opp_text or ""):
                        matched_industry_kw = kw
                        break
                if matched_industry_kw:
                    break
            if matched_industry_kw:
                reasons.append(f"산업 적합: {industry} (공고: '{matched_industry_kw}')")
            else:
                reasons.append(f"산업 적합: {industry or '해당 분야'}")

    # 고객군
    if rule_scores.get("customer", 0) > 0:
        opp_agency = opportunity.get("agency")
        if opp_agency:
            reasons.append(f"발주/고객 매칭: {opp_agency}")

    return reasons


def _similarity_component(similarity: float | None) -> int:
    """임베딩 코사인 유사도 → tech 가산점 (0~SIM_MAX).

    similarity None이면 0 반환(규칙 전용 경로 불변).
    SIM_FLOOR~SIM_CEIL 대역을 0~SIM_MAX로 선형 재스케일.
    """
    if similarity is None:
        return 0
    clamped = max(0.0, min(1.0, (similarity - SIM_FLOOR) / (SIM_CEIL - SIM_FLOOR)))
    return round(clamped * SIM_MAX)


# ── 공개 API ────────────────────────────────────────────────────────────────

def retrieve_candidates(
    db: Session, company_context_id: str, top_n: int | None = None
) -> list[tuple[str, float]]:
    """① 검색: 기업 벡터로 opportunities 후보 압축(status=open 필터, pgvector).

    반환: (opportunity_id, similarity) 튜플 리스트. 기업 벡터를 행에서 읽어
    코사인 유사도 top-N 검색. 기업 벡터 없으면 빈 리스트.
    """
    top_n = top_n or settings.match_retrieval_top_n
    company_vector = vectorstore.get_embedding(
        db, vectorstore.COMPANY_CONTEXTS, company_context_id
    )
    if company_vector is None:
        return []
    # dedup 대표(is_canonical)만 후보로 — 중복본이 추천에 끼지 않도록(display-dedup.md §4).
    return vectorstore.search_opportunities(
        db, company_vector, limit=top_n, status="open", canonical_only=True
    )


def score_match(
    company_context: dict,
    opportunity: dict,
    presets: dict[str, int],
    *,
    llm_complete_json: Callable | None = None,
    similarity: float | None = None,
) -> ScoreResult:
    """② 스코어링: 규칙 sub-score(presets) 주입 + LLM 실적유사도·근거 생성.

    Args:
        company_context:   CONTEXT_SCHEMA 형태의 기업 역량 dict.
        opportunity:       공고 정보 dict (title, agency, region, category, description, id 등).
        presets:           규칙으로 계산한 {region, industry, tech, customer} 사전 점수.
                           빈 dict이면 내부에서 자동 계산.
        llm_complete_json: 주입 가능한 LLM 호출 함수 (테스트 모킹용).
                           None이면 app.services.llm.complete_json 사용.
        similarity:        pgvector 코사인 유사도(0~1). None이면 임베딩 가산 없음.
                           규칙 경로(LLM tech 미반환)의 tech 점수에 _similarity_component
                           를 더해 공고별 점수 분산 효과. LLM tech 반환 시 LLM 값 우선.

    Returns:
        ScoreResult: score(0~100), reasons, subscore, risk.

    Notes:
        LLM 키 없으면 규칙 점수만으로 결과 반환(track=0, risk에 경고 표시).
    """
    # presets 없으면 규칙 계산; presets 명시 값이 있으면 해당 차원만 덮어씀
    computed = _compute_rule_presets(company_context, opportunity)
    rule_scores = {**computed, **presets}

    opp_id = str(opportunity.get("id", ""))

    # ── LLM sub-score (실적유사도·고객맥락·근거) ───────────────────────────
    track_score = 0
    reasons: list[str] = []
    risk: str | None = None
    llm_subscores: dict[str, int] = {}

    if llm_complete_json is None:
        # LLM 없음 → 규칙 기반 템플릿 근거 생성
        reasons = _build_rule_reasons(company_context, opportunity, rule_scores)
        risk = "LLM 미사용(규칙 기반 점수)"
    else:
        try:
            system_prompt = (
                "당신은 공공조달 전문 매칭 AI다. "
                "기업의 수행실적과 공고 요건을 분석해 적합도를 판단한다. "
                "사실에 근거해 평가하고, 없는 정보는 만들지 마라. "
                "근거(reasons)는 핵심만 간결하게 2~3개, 각 한 문장으로 제시한다."
            )
            user_prompt = (
                f"## 기업 역량\n{_format_context(company_context)}\n\n"
                f"## 규칙 사전 점수\n"
                f"- 지역 일치: {rule_scores.get('region', 0)}/10\n"
                f"- 산업 일치: {rule_scores.get('industry', 0)}/15\n"
                f"- 기술 키워드: {rule_scores.get('tech', 0)}/30(규칙)\n"
                f"- 고객군 일치: {rule_scores.get('customer', 0)}/20\n\n"
                f"## 평가 대상 공고\n{_format_opportunity(opportunity)}\n\n"
                "위 정보를 바탕으로 structured_output 도구를 사용해 평가 결과를 반환하라.\n"
                "subscores.track(0~25): 수행실적 유사도.\n"
                "subscores.tech(0~30): 기술 일치(규칙 점수 참고 후 재평가).\n"
                "subscores.customer(0~20): 고객군 일치(규칙 점수 참고 후 재평가).\n"
                "subscores.industry(0~15): 산업 일치(규칙 점수 그대로 사용 가능).\n"
                "subscores.region(0~10): 지역 일치(규칙 점수 그대로 사용 가능).\n"
                "reasons: 핵심 근거 2~3개(각 한 문장, 간결하게 — 중복·군더더기 금지).\n"
                "risk: 리스크 있으면 한 줄, 없으면 빈 문자열.\n"
                f"opportunity_id: \"{opp_id}\""
            )
            llm_result = llm_complete_json(system_prompt, user_prompt, _LLM_SCHEMA)
            llm_subscores = llm_result.get("subscores", {})
            track_score = int(llm_subscores.get("track", 0))
            reasons = llm_result.get("reasons", [])
            risk_raw = llm_result.get("risk", "")
            risk = risk_raw if risk_raw else None
        except RuntimeError as exc:
            logger.warning("LLM 미사용 (키 없음 또는 오류): %s — 규칙 점수만 적용", exc)
            reasons = _build_rule_reasons(company_context, opportunity, rule_scores)
            risk = "LLM 미사용(규칙 기반 점수)"
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLM 스코어링 실패: %s — 규칙 점수만 적용", exc)
            reasons = _build_rule_reasons(company_context, opportunity, rule_scores)
            risk = f"LLM 오류: {exc}"

    # ── 가중합 ──────────────────────────────────────────────────────────────
    # LLM이 subscores를 반환했으면 우선, 없으면 규칙값 폴백.
    # LLM tech 미반환 시 규칙 tech에 임베딩 유사도 가산(similarity 있을 때만).
    keyword_tech = rule_scores.get("tech", 0)
    if "tech" not in llm_subscores and similarity is not None:
        keyword_tech = min(WEIGHTS["tech"], keyword_tech + _similarity_component(similarity))
    final_tech     = int(llm_subscores.get("tech", keyword_tech))
    final_track    = track_score
    final_customer = int(llm_subscores.get("customer", rule_scores.get("customer", 0)))
    final_industry = int(llm_subscores.get("industry", rule_scores.get("industry", 0)))
    final_region   = int(llm_subscores.get("region",   rule_scores.get("region", 0)))

    # 범위 클리핑
    final_tech     = min(WEIGHTS["tech"],     max(0, final_tech))
    final_track    = min(WEIGHTS["track"],    max(0, final_track))
    final_customer = min(WEIGHTS["customer"], max(0, final_customer))
    final_industry = min(WEIGHTS["industry"], max(0, final_industry))
    final_region   = min(WEIGHTS["region"],   max(0, final_region))

    total = final_tech + final_track + final_customer + final_industry + final_region
    score = min(100, max(0, total))

    subscore_out = {
        "tech":     final_tech,
        "track":    final_track,
        "customer": final_customer,
        "industry": final_industry,
        "region":   final_region,
    }

    return ScoreResult(score=score, reasons=reasons, subscore=subscore_out, risk=risk)


# ── 포맷 헬퍼 ───────────────────────────────────────────────────────────────

def _format_context(ctx: dict) -> str:
    lines = []
    if ctx.get("industry"):
        lines.append(f"- 대표 산업: {ctx['industry']}")
    if ctx.get("capable_industries"):
        names = [ksic_name(c) for c in ctx["capable_industries"] if ksic_name(c) and c != KSIC_ETC]
        if names:
            lines.append(f"- 수행 업종(표준): {', '.join(names)}")
    if ctx.get("technologies"):
        lines.append(f"- 기술: {', '.join(ctx['technologies'])}")
    if ctx.get("customers"):
        lines.append(f"- 주요 고객: {', '.join(ctx['customers'])}")
    if ctx.get("regions"):
        lines.append(f"- 지역: {', '.join(ctx['regions'])}")
    if ctx.get("track_records"):
        trs = ctx["track_records"]
        tr_texts = []
        for tr in trs[:5]:  # 최대 5건
            if isinstance(tr, dict):
                tr_texts.append(
                    f"  * {tr.get('title', '')} ({tr.get('year', '')})"
                    + (f" — {tr.get('client', '')}" if tr.get('client') else "")
                )
            else:
                tr_texts.append(f"  * {tr}")
        lines.append("- 수행실적:\n" + "\n".join(tr_texts))
    if ctx.get("strengths"):
        lines.append(f"- 강점: {', '.join(ctx['strengths'])}")
    return "\n".join(lines) if lines else "(정보 없음)"


def _format_opportunity(opp: dict) -> str:
    lines = []
    if opp.get("title"):
        lines.append(f"- 공고명: {opp['title']}")
    if opp.get("agency"):
        lines.append(f"- 발주기관: {opp['agency']}")
    if opp.get("category"):
        lines.append(f"- 유형: {opp['category']}")
    if opp.get("industry") and opp["industry"] != KSIC_ETC:
        lines.append(f"- 업종(표준): {ksic_name(opp['industry'])}")
    if opp.get("region"):
        lines.append(f"- 지역: {opp['region']}")
    if opp.get("description"):
        desc = opp["description"]
        lines.append(f"- 설명: {desc[:500]}" + ("..." if len(desc) > 500 else ""))
    return "\n".join(lines) if lines else "(정보 없음)"
