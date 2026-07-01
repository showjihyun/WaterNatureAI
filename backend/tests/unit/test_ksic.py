"""단위 테스트: KSIC 업종 분류 + 키워드 매처(부분문자열 오매칭 방지).

순수 룰(DB/HTTP 없음). 회귀 초점: '마트'⊂'스마트', 'AI'⊂'AIR' 등
부분문자열로 인한 업종 오분류를 차단하는지.
"""
from __future__ import annotations

from app.services.ksic import classify_industry, keyword_in_text


class TestKeywordMatcher:
    def test_korean_substring_matches(self):
        assert keyword_in_text("폐기물", "생활 폐기물 수집운반 용역")

    def test_mart_not_inside_smart(self):
        """'마트'(도소매)는 '스마트'(smart) 안에서 매칭되지 않는다 — 핵심 회귀."""
        assert not keyword_in_text("마트", "스마트공장 통합관제 구축")
        assert not keyword_in_text("마트", "스마트시티 플랫폼")

    def test_mart_matches_real_retail(self):
        """실제 도소매 맥락의 '마트'는 정상 매칭(이마트·시장/마트 등)."""
        assert keyword_in_text("마트", "전통시장·마트 상생 지원")
        assert keyword_in_text("마트", "이마트 입점 지원 사업")

    def test_ascii_acronym_word_boundary_blocks_infix(self):
        """영문 약어는 더 긴 영단어 안에서 매칭되지 않는다(단어경계)."""
        assert not keyword_in_text("AI", "AIR 공조설비 유지보수")
        assert not keyword_in_text("AI", "MAINTENANCE 용역")
        assert not keyword_in_text("GIS", "LOGISTICS 센터 운영")
        assert not keyword_in_text("ICT", "DISTRICT 정비 사업")

    def test_ascii_acronym_matches_standalone(self):
        """경계가 맞으면(공백·한글·문자열 경계) 정상 매칭."""
        assert keyword_in_text("AI", "AI 기반 분석 시스템")
        assert keyword_in_text("AI", "차세대 AI시스템 구축")  # 한글 경계
        assert keyword_in_text("GIS", "GIS 공간정보 구축")

    def test_ascii_case_insensitive(self):
        """대소문자 무시 — 소문자 표기도 매칭(기존 case-sensitive miss 해소)."""
        assert keyword_in_text("API", "공공 api 연계 시스템")
        assert keyword_in_text("SaaS", "saas 전환 사업")

    def test_empty_inputs(self):
        assert not keyword_in_text("", "텍스트")
        assert not keyword_in_text("AI", "")


class TestClassifyIndustry:
    def test_smart_factory_not_misclassified_as_retail(self):
        """'스마트공장' IT 공고가 '마트'(도소매 G)로 오분류되지 않는다."""
        assert classify_industry("스마트공장 통합관제 플랫폼 구축", source="narajangter") != "G"

    def test_air_maintenance_not_misclassified_as_it(self):
        """'AIR ...'가 'AI'(IT J) substring 으로 오분류되지 않는다."""
        assert classify_industry("AIR 공조설비 유지보수", source="narajangter") != "J"

    def test_it_keywords_classify_j(self):
        assert classify_industry("정보시스템 구축 및 소프트웨어 개발") == "J"

    def test_environment_keywords_classify_e(self):
        assert classify_industry("하수처리장 수질개선 및 폐기물 처리") == "E"

    def test_construction_category_prior(self):
        assert classify_industry("도로 포장공사", category="공사") == "F"

    def test_never_returns_none(self):
        assert classify_industry(None) == "ETC"
        assert classify_industry("") == "ETC"
