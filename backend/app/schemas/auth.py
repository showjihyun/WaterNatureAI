"""인증 스키마 (FR-001·002)."""
from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    company_name: str = Field(min_length=1, max_length=255)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenOut(BaseModel):
    """HTTP 응답용 — access 토큰만 본문에 반환. refresh 토큰은 httpOnly 쿠키로 전달."""

    access_token: str
    token_type: str = "bearer"
