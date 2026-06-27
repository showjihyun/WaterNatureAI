"""인증 라우터 (FR-001·002). 상세: docs/04-architecture/auth-onboarding.md §8."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import DbSession
from app.api.ratelimit import rate_limit
from app.schemas.auth import LoginIn, RefreshIn, RegisterIn, TokenOut
from app.services import auth_service

router = APIRouter()


@router.post(
    "/register",
    response_model=TokenOut,
    status_code=201,
    dependencies=[Depends(rate_limit("register", limit=5, window_sec=60))],
)
def register(body: RegisterIn, db: DbSession) -> TokenOut:
    return auth_service.register(
        db, email=body.email, password=body.password, company_name=body.company_name
    )


@router.post(
    "/login",
    response_model=TokenOut,
    dependencies=[Depends(rate_limit("login", limit=10, window_sec=60))],
)
def login(body: LoginIn, db: DbSession) -> TokenOut:
    return auth_service.login(db, email=body.email, password=body.password)


@router.post(
    "/refresh",
    response_model=TokenOut,
    dependencies=[Depends(rate_limit("refresh", limit=30, window_sec=60))],
)
def refresh(body: RefreshIn, db: DbSession) -> TokenOut:
    return auth_service.refresh(db, refresh_token=body.refresh_token)


@router.post("/logout", status_code=204)
def logout(body: RefreshIn, db: DbSession) -> None:
    auth_service.logout(db, refresh_token=body.refresh_token)
