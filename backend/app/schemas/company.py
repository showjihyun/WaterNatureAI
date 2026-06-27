"""회사 프로필/온보딩 스키마 (FR-003·company-brain). 정본: auth-onboarding.md, company-brain.md."""
from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import BaseModel, Field


class CompanyProfileIn(BaseModel):
    """프로필 부분 수정 — 전달된 필드만 업데이트(전부 선택)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    industry: str | None = Field(default=None, max_length=255)
    description: str | None = None
    region: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=32)

    # 온보딩 프로필 (0004) — Company Brain 입력
    services: list[str] | None = None
    technologies: list[str] | None = None
    customers: list[str] | None = None
    certifications: list[str] | None = None

    # 수행 역량 (0002)
    tech_level: Annotated[int | None, Field(default=None, ge=1, le=5)] = None
    max_project_budget: int | None = None
    capable_categories: list[str] | None = None


class CompanyProfileOut(BaseModel):
    id: uuid.UUID
    name: str
    industry: str | None = None
    description: str | None = None
    region: str | None = None
    phone: str | None = None
    onboarding_status: str

    # 온보딩 프로필 (0004)
    services: list[str] | None = None
    technologies: list[str] | None = None
    customers: list[str] | None = None
    certifications: list[str] | None = None

    # 회사소개서 (0005, FR-004) — 파일명만 노출(추출 텍스트 본문은 미반환)
    document_filename: str | None = None

    # 수행 역량 (0002)
    tech_level: int | None = None
    max_project_budget: int | None = None
    capable_categories: list[str] | None = None

    model_config = {"from_attributes": True}
