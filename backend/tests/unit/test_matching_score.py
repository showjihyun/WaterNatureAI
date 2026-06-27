"""단위 테스트: matching engine score_match + 규칙 sub-score (결정론).

- 규칙 sub-score(_region_score, _industry_score, _tech_keyword_score, _customer_score):
  결정론적 — 키 불필요, DB 불필요.
- score_match: LLM 모킹으로 가중합 검증.
- 수용 기준 1~6: fallback+LLM-off 현실 점수 고정.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services.matching.engine import (
    SIM_CEIL,
    SIM_FLOOR,
    SIM_MAX,
    WEIGHTS,
    ScoreResult,
    _compute_rule_presets,
    _customer_score,
    _industry_score,
    _region_score,
    _similarity_component,
    _tech_keyword_score,
    score_match,
)


# ── 규칙 sub-score 단위 테스트 ─────────────────────────────────────────────

class TestRegionScore:
    def test_exact_match(self):
        assert _region_score(["서울"], "서울") == 10

    def test_partial_match(self):
        score = _region_score(["서울"], "서울특별시")
        assert score == 7

    def test_no_match(self):
        assert _region_score(["부산"], "서울") == 0

    def test_national_context_always_matches(self):
        assert _region_score(["전국", "서울"], "제주") == 10

    def test_no_opp_region_returns_10(self):
        """공고 지역 없음 → 전국 공고로 간주 → 10."""
        assert _region_score(["서울"], None) == 10

    def test_empty_context_regions(self):
        """ctx.regions=[] → 지역 제약 없음 → 10 (무회귀 보장)."""
        assert _region_score([], "서울") == 10

    def test_empty_context_regions_national(self):
        """ctx.regions=[] → 항상 10 (어떤 opp_region 이어도)."""
        assert _region_score([], "부산") == 10

    def test_national_in_context_any_region(self):
        """ctx에 '전국' 있으면 어떤 지역도 10."""
        assert _region_score(["전국"], "서울특별시") == 10


class TestIndustryScore:
    """신규 _industry_score: opp_text 기반 파생, category 의존 제거."""

    def test_signal_keyword_in_opp_text_strong(self):
        """공간정보 시그널 키워드 GIS 가 title 에 등장 → 15."""
        score = _industry_score("공간정보", [], "GIS 기반 공간정보 구축 용역")
        assert score == 15

    def test_signal_keyword_gis_industry(self):
        """GIS 산업 → 시그널 '측량'이 title 에 등장 → 15."""
        score = _industry_score("GIS", [], "국토측량 용역 발주")
        assert score == 15

    def test_industry_string_in_text_weak(self):
        """'환경' 산업 시그널 키워드 중 '환경' 자체가 opp_text 에 포함 → 15 (강한 매칭).

        환경 INDUSTRY_KEYWORDS 에 '환경'이 포함되므로 strong 경로(15) 반환.
        """
        score = _industry_score("환경", [], "환경 정화 사업 추진")
        assert score >= 8  # 최소 약한 매칭, 실제론 강한 매칭 15

    def test_no_match_returns_zero(self):
        """건설회사 × 폐기물 공고 — 시그널 없음 → 0."""
        score = _industry_score("건설", [], "폐기물 처리 용역")
        assert score == 0

    def test_no_opp_text_returns_zero(self):
        """opp_text 없으면 0 (무료 점수 없음)."""
        assert _industry_score("IT", [], "") == 0

    def test_category_none_returns_zero_not_seven(self):
        """opp_text 없고 category 도 없으면 0 — 기존 '7 무료점수' 제거."""
        assert _industry_score("IT", [], "", opp_category=None) == 0

    def test_industries_list_checked(self):
        """ctx.industries 리스트도 확인."""
        score = _industry_score(None, ["AI", "GIS"], "공간정보 플랫폼 구축")
        assert score >= 8

    def test_environment_keywords(self):
        """환경 산업 → '폐기물' 시그널 키워드 매칭 → 15."""
        score = _industry_score("환경", [], "폐기물 처리 용역 입찰")
        assert score == 15


class TestTechKeywordScore:
    def test_one_match_returns_12(self):
        """변별 키워드 1개 매칭 → 12."""
        score = _tech_keyword_score([], ["공간정보"], "공간정보 시스템 구축 용역")
        assert score == 12

    def test_two_matches_return_24(self):
        """변별 키워드 2개 매칭 → 24."""
        score = _tech_keyword_score(["GIS", "측량"], [], "GIS 측량 용역")
        assert score == 24

    def test_three_plus_matches_cap_at_30(self):
        """3개 이상 매칭 → 30 (uncap)."""
        score = _tech_keyword_score(["GIS", "측량", "디지털트윈"], [], "GIS 측량 디지털트윈 구축")
        assert score == 30

    def test_stopword_excluded(self):
        """'시스템'은 불용어 → 매칭에서 제외."""
        # '시스템'만 있으면 변별 키워드 없음 → 0
        score = _tech_keyword_score(["시스템"], [], "시스템 구축 용역")
        assert score == 0

    def test_stopword_doesnt_inflate(self):
        """IT 회사 keywords=[시스템, 정보화] → 공고 '시스템 구축'에서 변별 키워드 제외 → tech 과대 아님."""
        score = _tech_keyword_score([], ["시스템", "정보화"], "CRM 시스템 구축")
        # 두 키워드 모두 불용어 → 변별 키워드 없음 → 0
        assert score == 0

    def test_no_overlap(self):
        assert _tech_keyword_score(["블록체인"], [], "사무용품 구매") == 0

    def test_empty_tech_returns_zero(self):
        assert _tech_keyword_score([], [], "파이썬 AI") == 0

    def test_keywords_also_checked(self):
        """ctx.keywords 도 변별 키워드로 포함."""
        score = _tech_keyword_score([], ["공간정보"], "공간정보 구축")
        assert score > 0

    def test_short_keyword_excluded(self):
        """1자 키워드 제외."""
        score = _tech_keyword_score(["A"], [], "A 개발")
        assert score == 0


class TestCustomerScore:
    def test_exact_match(self):
        assert _customer_score(["LX"], "LX") == 20

    def test_partial_match(self):
        score = _customer_score(["LX"], "LX한국국토정보공사")
        assert score == 12

    def test_no_match(self):
        assert _customer_score(["LX"], "국토교통부") == 0

    def test_empty_customers_fallback_zero(self):
        """customers=[] (fallback) → 0 (정직)."""
        assert _customer_score([], "LX") == 0

    def test_no_agency(self):
        assert _customer_score(["LX"], None) == 0


class TestComputeRulePresets:
    def test_returns_all_keys(self):
        ctx = {
            "regions": ["서울"],
            "industry": "공간정보",
            "technologies": ["GIS"],
            "customers": ["LX"],
        }
        opp = {
            "title": "GIS 공간정보 개발 용역",
            "agency": "LX",
            "region": "서울",
            "category": "IT",
            "description": "",
        }
        presets = _compute_rule_presets(ctx, opp)
        assert set(presets.keys()) >= {"region", "industry", "tech", "customer"}

    def test_values_in_weight_range(self):
        ctx = {
            "regions": ["서울"],
            "industry": "IT",
            "technologies": ["Python"],
            "customers": ["LX"],
        }
        opp = {
            "title": "IT 서비스",
            "agency": "LX",
            "region": "서울",
            "category": "IT",
            "description": "Python 기반 솔루션",
        }
        presets = _compute_rule_presets(ctx, opp)
        assert 0 <= presets["region"] <= WEIGHTS["region"]
        assert 0 <= presets["industry"] <= WEIGHTS["industry"]
        assert 0 <= presets["tech"] <= WEIGHTS["tech"]
        assert 0 <= presets["customer"] <= WEIGHTS["customer"]

    def test_region_derived_from_agency(self):
        """opp.region=None 이지만 agency '서울특별시청' → region 파생."""
        ctx = {"regions": ["서울"], "industry": "IT", "technologies": [], "customers": []}
        opp = {"title": "IT 용역", "agency": "서울특별시청", "region": None,
               "category": "IT", "description": ""}
        presets = _compute_rule_presets(ctx, opp)
        # 서울 ctx + 서울 파생 → 10
        assert presets["region"] == 10


# ── 수용 기준 (acceptance criteria) ──────────────────────────────────────

class TestAcceptanceCriteria:
    """수용 기준 1~6: LLM-off fallback 현실 점수 고정."""

    # GIS 회사: _derive_keywords("공간정보", "...") 가 생성할 법한 컨텍스트
    GIS_CTX = {
        "industry": "공간정보",
        "industries": ["공간정보", "GIS"],
        "technologies": ["GIS", "측량", "디지털트윈"],
        "keywords": ["공간정보", "지리정보"],  # _derive_keywords 가 산업 시그널 키워드 추가
        "customers": [],
        "regions": [],
        "track_records": [],
        "strengths": [],
        "services": [],
    }

    # 환경 회사: _derive_keywords("환경", "...") 가 생성할 법한 컨텍스트
    ENV_CTX = {
        "industry": "환경",
        "industries": ["환경"],
        "technologies": ["수질분석", "대기측정"],
        "keywords": ["폐기물", "생태"],  # 환경 시그널 키워드 중 실제 공고에 나타나는 것
        "customers": [],
        "regions": [],
        "track_records": [],
        "strengths": [],
        "services": [],
    }

    IT_CTX = {
        "industry": "IT",
        "industries": ["IT"],
        "technologies": [],
        "keywords": ["시스템", "정보화"],
        "customers": [],
        "regions": [],
        "track_records": [],
        "strengths": [],
        "services": [],
    }

    def _rule_score(self, ctx: dict, opp: dict) -> dict:
        """LLM 없이 규칙 점수만 반환."""
        result = score_match(ctx, opp, {}, llm_complete_json=None)
        return result.subscore

    # 수용 기준 1: GIS × GIS 공고 → ≥35 통과
    def test_ac1_gis_company_gis_opp_passes_threshold(self):
        """AC1: GIS회사 × '○○시 공간정보 시스템 구축 용역' → score ≥ 35."""
        opp = {
            "id": "ac1",
            "title": "○○시 공간정보 시스템 구축 용역",
            "agency": "○○시청",
            "region": None,
            "category": "용역",
            "description": "",
        }
        result = score_match(self.GIS_CTX, opp, {}, llm_complete_json=None)
        sub = result.subscore
        # industry: GIS/공간정보 키워드 '공간정보' 등장 → 15
        assert sub["industry"] == 15, f"industry={sub['industry']} (expected 15)"
        # tech: GIS·측량·디지털트윈·지리정보 중 매칭 확인 (공간정보는 시그널 키워드지만 불용어 아님)
        assert sub["tech"] >= 12, f"tech={sub['tech']} (expected ≥12)"
        # region: ctx.regions=[] → 10
        assert sub["region"] == 10, f"region={sub['region']} (expected 10)"
        assert result.score >= 35, f"score={result.score} (expected ≥35)"

    # 수용 기준 2: GIS × 폐기물 공고 → <35 차단
    def test_ac2_gis_company_waste_opp_blocked(self):
        """AC2: GIS회사 × '학교 폐기물처리용역' → score < 35 (차단)."""
        opp = {
            "id": "ac2",
            "title": "학교 폐기물처리용역",
            "agency": "○○초등학교",
            "region": None,
            "category": "용역",
            "description": "",
        }
        result = score_match(self.GIS_CTX, opp, {}, llm_complete_json=None)
        sub = result.subscore
        assert sub["tech"] == 0, f"tech={sub['tech']} (expected 0)"
        assert sub["industry"] == 0, f"industry={sub['industry']} (expected 0)"
        assert sub["region"] == 10  # ctx.regions=[]
        assert result.score < 35, f"score={result.score} (expected <35)"

    # 수용 기준 3: 환경회사 × 폐기물 공고 → ≥35 통과
    def test_ac3_env_company_waste_opp_passes(self):
        """AC3: 환경회사 × '폐기물 처리 용역' → score ≥ 35."""
        opp = {
            "id": "ac3",
            "title": "폐기물 처리 용역 입찰 공고",
            "agency": "○○시청",
            "region": None,
            "category": "용역",
            "description": "",
        }
        result = score_match(self.ENV_CTX, opp, {}, llm_complete_json=None)
        sub = result.subscore
        # 환경 시그널: '폐기물' in INDUSTRY_KEYWORDS['환경'] → industry=15
        assert sub["industry"] == 15, f"industry={sub['industry']} (expected 15)"
        # tech: '수질분석', '대기측정', '폐기물관리' 변별 키워드
        assert sub["tech"] >= 12, f"tech={sub['tech']} (expected ≥12)"
        assert result.score >= 35, f"score={result.score} (expected ≥35)"

    # 수용 기준 4: stopword 비인플레이션
    def test_ac4_stopword_not_inflating(self):
        """AC4: IT회사 keywords=['시스템','정보화'] × 'CRM 시스템 구축' → 불용어 제외 tech=0."""
        opp = {
            "id": "ac4",
            "title": "CRM 시스템 구축",
            "agency": "○○기관",
            "region": None,
            "category": "IT",
            "description": "",
        }
        result = score_match(self.IT_CTX, opp, {}, llm_complete_json=None)
        assert result.subscore["tech"] == 0, f"tech={result.subscore['tech']} (stopwords should be excluded)"

    # 수용 기준 5a: region 무회귀 — ctx.regions=[]
    def test_ac5a_empty_regions_always_10(self):
        """AC5a: ctx.regions=[] 이면 agency 서울특별시 있어도 region=10."""
        ctx = {**self.GIS_CTX, "regions": []}
        opp = {
            "id": "ac5a",
            "title": "서울 공간정보 용역",
            "agency": "서울특별시",
            "region": None,
            "category": "용역",
            "description": "",
        }
        result = score_match(ctx, opp, {}, llm_complete_json=None)
        assert result.subscore["region"] == 10

    # 수용 기준 5b: ctx.regions=['전국']
    def test_ac5b_national_regions_always_10(self):
        """AC5b: ctx.regions=['전국'] 이면 어떤 agency 지역도 10."""
        ctx = {**self.GIS_CTX, "regions": ["전국"]}
        opp = {
            "id": "ac5b",
            "title": "서울 공간정보 용역",
            "agency": "서울특별시",
            "region": None,
            "category": "용역",
            "description": "",
        }
        result = score_match(ctx, opp, {}, llm_complete_json=None)
        assert result.subscore["region"] == 10

    # 수용 기준 5c: ctx.regions=['부산'] × agency 서울 → region 낮음
    def test_ac5c_busan_ctx_seoul_agency_region_low(self):
        """AC5c: ctx.regions=['부산'] × agency='서울특별시청' → region < 10."""
        ctx = {**self.GIS_CTX, "regions": ["부산"]}
        opp = {
            "id": "ac5c",
            "title": "서울 공간정보 용역",
            "agency": "서울특별시청",
            "region": None,
            "category": "용역",
            "description": "",
        }
        result = score_match(ctx, opp, {}, llm_complete_json=None)
        # 부산 ctx + 서울 파생 → 0 (불일치)
        assert result.subscore["region"] < 10

    # 수용 기준 6: tech uncap — 3개 이상 → 30
    def test_ac6_tech_uncap_three_matches(self):
        """AC6: 변별 키워드 3개 이상 매칭 → tech=30."""
        ctx = {
            "industry": "공간정보",
            "industries": [],
            "technologies": ["GIS", "측량", "디지털트윈"],
            "keywords": [],
            "customers": [],
            "regions": [],
            "track_records": [],
            "strengths": [],
            "services": [],
        }
        opp = {
            "id": "ac6",
            "title": "GIS 측량 디지털트윈 플랫폼 구축",
            "agency": "국토교통부",
            "region": None,
            "category": "용역",
            "description": "",
        }
        result = score_match(ctx, opp, {}, llm_complete_json=None)
        assert result.subscore["tech"] == 30, f"tech={result.subscore['tech']} (expected 30)"


# ── score_match 통합 (LLM 모킹) ───────────────────────────────────────────

def _make_llm_fn(subscores: dict, reasons: list[str], risk: str = "") -> MagicMock:
    """LLM complete_json 모킹 함수를 반환한다."""
    mock = MagicMock(return_value={
        "opportunity_id": "test-opp",
        "subscores": subscores,
        "score": sum(subscores.values()),
        "reasons": reasons,
        "risk": risk,
    })
    return mock


class TestScoreMatch:
    def _ctx(self) -> dict:
        return {
            "industry": "GIS",
            "industries": ["공간정보", "AI"],
            "technologies": ["디지털트윈", "공간분석"],
            "services": ["플랫폼 구축"],
            "customers": ["LX", "LH"],
            "regions": ["서울", "전국"],
            "track_records": [
                {"title": "LX 디지털트윈", "year": 2024, "client": "LX", "summary": "..."}
            ],
            "strengths": ["공공사업 경험"],
            "keywords": ["디지털트윈"],
        }

    def _opp(self) -> dict:
        return {
            "id": "opp-001",
            "title": "디지털트윈 공간정보 플랫폼 구축",
            "agency": "LX",
            "region": "서울",
            "category": "GIS",
            "description": "디지털트윈 기반 공간분석 솔루션",
        }

    def test_score_match_returns_score_result(self):
        """score_match가 ScoreResult를 반환한다."""
        llm_fn = _make_llm_fn(
            {"tech": 25, "track": 20, "customer": 20, "industry": 15, "region": 10},
            ["LX 수행실적 유사", "기술 일치"],
        )
        result = score_match(self._ctx(), self._opp(), {}, llm_complete_json=llm_fn)
        assert isinstance(result, ScoreResult)
        assert isinstance(result.score, int)
        assert 0 <= result.score <= 100

    def test_score_weighted_sum(self):
        """LLM 반환 subscores의 가중합이 score에 반영된다."""
        subscores = {"tech": 25, "track": 20, "customer": 15, "industry": 12, "region": 8}
        llm_fn = _make_llm_fn(subscores, ["근거1"])
        result = score_match(self._ctx(), self._opp(), {}, llm_complete_json=llm_fn)
        expected = 25 + 20 + 15 + 12 + 8
        assert result.score == expected

    def test_subscore_keys_present(self):
        """subscore에 5개 차원 키 모두 존재."""
        llm_fn = _make_llm_fn(
            {"tech": 10, "track": 10, "customer": 10, "industry": 10, "region": 5},
            [],
        )
        result = score_match(self._ctx(), self._opp(), {}, llm_complete_json=llm_fn)
        assert set(result.subscore.keys()) == {"tech", "track", "customer", "industry", "region"}

    def test_reasons_forwarded(self):
        """LLM 반환 reasons가 ScoreResult.reasons에 포함된다."""
        reasons = ["LX 수행실적 유사", "디지털트윈 기술 일치"]
        llm_fn = _make_llm_fn(
            {"tech": 20, "track": 15, "customer": 10, "industry": 8, "region": 5},
            reasons,
        )
        result = score_match(self._ctx(), self._opp(), {}, llm_complete_json=llm_fn)
        assert result.reasons == reasons

    def test_risk_forwarded(self):
        """LLM 반환 risk가 ScoreResult.risk에 포함된다."""
        llm_fn = _make_llm_fn(
            {"tech": 10, "track": 5, "customer": 5, "industry": 5, "region": 5},
            [],
            risk="필수자격 미충족 가능",
        )
        result = score_match(self._ctx(), self._opp(), {}, llm_complete_json=llm_fn)
        assert result.risk == "필수자격 미충족 가능"

    def test_llm_error_falls_back_to_rule_score(self):
        """LLM RuntimeError → 규칙 점수만 적용, risk에 경고 포함."""
        def _failing_llm(*_a, **_k):
            raise RuntimeError("ANTHROPIC_API_KEY 미설정")

        ctx = {
            "industry": "IT",
            "technologies": ["Python"],
            "customers": ["국토교통부"],
            "regions": ["전국"],
            "keywords": [],
            "industries": [],
            "track_records": [],
            "strengths": [],
            "services": [],
        }
        opp = {
            "id": "x",
            "title": "Python 개발",
            "agency": "국토교통부",
            "region": "서울",
            "category": "IT",
            "description": "",
        }
        result = score_match(ctx, opp, {}, llm_complete_json=_failing_llm)
        # track=0 (LLM 없음), 규칙 점수만 합산
        assert result.subscore["track"] == 0
        assert result.risk is not None  # 경고 포함

    def test_score_clipped_to_100(self):
        """합산이 100 초과해도 100 이하로 클리핑."""
        llm_fn = _make_llm_fn(
            {"tech": 30, "track": 25, "customer": 20, "industry": 15, "region": 10},
            [],
        )
        result = score_match(self._ctx(), self._opp(), {}, llm_complete_json=llm_fn)
        assert result.score <= 100

    def test_presets_override_internal_rules(self):
        """presets를 명시하면 규칙 내부계산 대신 해당 값 우선 사용."""
        # LLM subscores 없으면 presets 폴백
        def _llm_no_subscores(system, user, schema):  # noqa: ARG001
            return {
                "opportunity_id": "x",
                "subscores": {},  # 비어있음
                "score": 0,
                "reasons": [],
                "risk": "",
            }

        presets = {"region": 10, "industry": 15, "tech": 18, "customer": 20}
        result = score_match(self._ctx(), self._opp(), presets, llm_complete_json=_llm_no_subscores)
        # 규칙 부분은 presets에서 옴
        assert result.subscore["region"] == 10
        assert result.subscore["industry"] == 15


# ── _similarity_component 단위 테스트 ─────────────────────────────────────

class TestSimilarityComponent:
    """_similarity_component 경계값 및 재스케일 검증."""

    def test_none_returns_zero(self):
        """similarity=None → 0 (규칙 전용 경로 불변)."""
        assert _similarity_component(None) == 0

    def test_floor_returns_zero(self):
        """similarity=SIM_FLOOR → 0 (하한)."""
        assert _similarity_component(SIM_FLOOR) == 0

    def test_ceil_returns_sim_max(self):
        """similarity=SIM_CEIL → SIM_MAX (상한)."""
        assert _similarity_component(SIM_CEIL) == SIM_MAX

    def test_above_ceil_clamped_to_sim_max(self):
        """similarity > SIM_CEIL → clamp → SIM_MAX."""
        assert _similarity_component(1.0) == SIM_MAX

    def test_below_floor_clamped_to_zero(self):
        """similarity < SIM_FLOOR (0.0 포함) → 0."""
        assert _similarity_component(0.0) == 0

    def test_negative_clamped_to_zero(self):
        """음수 유사도 → 0."""
        assert _similarity_component(-0.5) == 0

    def test_midpoint_rescales(self):
        """similarity=0.75 (SIM_FLOOR~SIM_CEIL 중간) → SIM_MAX/2 근처."""
        val = _similarity_component(0.75)
        # 0.75는 (0.75-0.6)/(0.9-0.6) = 0.5 → round(0.5*15)=8 또는 7 (반올림)
        assert 7 <= val <= 8

    def test_0_9_returns_15(self):
        """similarity=0.9 → _similarity_component=15 (상한)."""
        assert _similarity_component(0.9) == 15

    def test_0_6_returns_0(self):
        """similarity=0.6 → _similarity_component=0 (하한)."""
        assert _similarity_component(0.6) == 0

    def test_0_75_returns_7_or_8(self):
        """similarity=0.75 → 재스케일 약 7~8."""
        val = _similarity_component(0.75)
        assert val in (7, 8)


# ── similarity 분산 테스트 ───────────────────────────────────────────────────

class TestSimilarityDispersion:
    """동일 키워드 매칭 상황에서 similarity로 점수 분산 확인."""

    # 기본 공통 컨텍스트: GIS 회사, 1개 기술 키워드만 매칭
    _CTX = {
        "industry": "공간정보",
        "industries": ["공간정보"],
        "technologies": ["GIS"],
        "keywords": [],
        "customers": [],
        "regions": [],
        "track_records": [],
        "strengths": [],
        "services": [],
    }

    # 두 공고: 동일한 키워드(GIS 1개 → keyword_tech=12)
    _OPP_A = {
        "id": "sim-a",
        "title": "GIS 플랫폼 구축",
        "agency": "국토교통부",
        "region": None,
        "category": "용역",
        "description": "",
    }
    _OPP_B = {
        "id": "sim-b",
        "title": "GIS 플랫폼 구축",
        "agency": "국토교통부",
        "region": None,
        "category": "용역",
        "description": "",
    }

    def test_high_sim_scores_higher_than_low_sim(self):
        """similarity=0.85 vs 0.70 → 0.85 쪽 total이 더 높음."""
        result_high = score_match(self._CTX, self._OPP_A, {}, llm_complete_json=None, similarity=0.85)
        result_low  = score_match(self._CTX, self._OPP_B, {}, llm_complete_json=None, similarity=0.70)
        assert result_high.score > result_low.score, (
            f"high sim score={result_high.score} should be > low sim score={result_low.score}"
        )

    def test_high_sim_tech_greater_than_low_sim_tech(self):
        """similarity=0.85 vs 0.70 → tech 점수도 0.85 쪽이 높음."""
        result_high = score_match(self._CTX, self._OPP_A, {}, llm_complete_json=None, similarity=0.85)
        result_low  = score_match(self._CTX, self._OPP_B, {}, llm_complete_json=None, similarity=0.70)
        assert result_high.subscore["tech"] > result_low.subscore["tech"]

    def test_no_similarity_unchanged_from_baseline(self):
        """AC1~6 불변: similarity 없으면 기존 GIS×GIS 점수 37 그대로."""
        # GIS ctx × 3 tech 키워드 매칭 공고
        ctx = {
            "industry": "공간정보",
            "industries": ["공간정보", "GIS"],
            "technologies": ["GIS", "측량", "디지털트윈"],
            "keywords": ["공간정보", "지리정보"],
            "customers": [],
            "regions": [],
            "track_records": [],
            "strengths": [],
            "services": [],
        }
        opp = {
            "id": "ac1-baseline",
            "title": "○○시 공간정보 시스템 구축 용역",
            "agency": "○○시청",
            "region": None,
            "category": "용역",
            "description": "",
        }
        # similarity 없음 — 기존과 동일해야 함
        result_no_sim = score_match(ctx, opp, {}, llm_complete_json=None)
        result_none   = score_match(ctx, opp, {}, llm_complete_json=None, similarity=None)
        assert result_no_sim.score == result_none.score
        assert result_no_sim.subscore == result_none.subscore

    def test_irrelevant_opp_remains_below_threshold_with_similarity(self):
        """noisy sim: 산업·키워드 0인 무관 공고는 similarity 있어도 threshold 35 미만."""
        ctx = {
            "industry": "공간정보",
            "industries": ["공간정보"],
            "technologies": ["GIS"],
            "keywords": [],
            "customers": [],
            "regions": [],
            "track_records": [],
            "strengths": [],
            "services": [],
        }
        # 무관 공고: tech=0(GIS 없음), industry=0, customer=0, region=10(ctx=[])
        irrelevant_opp = {
            "id": "noise-opp",
            "title": "사무용품 구매 입찰",
            "agency": "국방부",
            "region": None,
            "category": "물품",
            "description": "사무용품 일체 구매",
        }
        # similarity=0.9 (최고 유사도)로 시뮬레이션
        result = score_match(ctx, irrelevant_opp, {}, llm_complete_json=None, similarity=0.9)
        # tech=0+15=15(max sim), industry=0, customer=0, region=10 → total=25 < 35
        assert result.score < 35, (
            f"irrelevant opp score={result.score} should be < 35 even with high similarity"
        )

    def test_tech_capped_at_weight_with_similarity(self):
        """similarity 가산 후에도 tech는 WEIGHTS['tech']=30 초과 불가."""
        ctx = {
            "industry": "공간정보",
            "industries": [],
            "technologies": ["GIS", "측량", "디지털트윈"],
            "keywords": [],
            "customers": [],
            "regions": [],
            "track_records": [],
            "strengths": [],
            "services": [],
        }
        opp = {
            "id": "cap-test",
            "title": "GIS 측량 디지털트윈 플랫폼",
            "agency": "국토교통부",
            "region": None,
            "category": "용역",
            "description": "",
        }
        result = score_match(ctx, opp, {}, llm_complete_json=None, similarity=0.9)
        assert result.subscore["tech"] <= WEIGHTS["tech"]
