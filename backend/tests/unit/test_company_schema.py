"""단위: 회사 프로필 스키마 검증 (CompanyProfileIn / CompanyProfileOut)."""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.company import CompanyProfileIn, CompanyProfileOut


class TestCompanyProfileIn:
    def test_all_fields_optional(self):
        """전부 선택 — 빈 입력도 유효(부분 수정 허용)."""
        body = CompanyProfileIn()
        assert body.model_dump(exclude_unset=True) == {}

    def test_partial_update_keeps_only_set_fields(self):
        body = CompanyProfileIn(phone="010-1234-5678")
        assert body.model_dump(exclude_unset=True) == {"phone": "010-1234-5678"}

    def test_full_payload(self):
        body = CompanyProfileIn(
            name="공간정보기업",
            industry="공간정보",
            description="GIS 전문",
            region="서울",
            phone="021234567",
        )
        dumped = body.model_dump(exclude_unset=True)
        assert dumped["name"] == "공간정보기업"
        assert set(dumped) == {"name", "industry", "description", "region", "phone"}

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            CompanyProfileIn(name="")

    def test_phone_too_long_rejected(self):
        with pytest.raises(ValidationError):
            CompanyProfileIn(phone="0" * 33)


class TestCompanyProfileOut:
    def test_from_attributes(self):
        class _Row:
            id = uuid.uuid4()
            name = "테스트기업"
            industry = None
            description = None
            region = None
            phone = None
            onboarding_status = "profile"

        out = CompanyProfileOut.model_validate(_Row())
        assert out.name == "테스트기업"
        assert out.onboarding_status == "profile"
        assert out.industry is None
