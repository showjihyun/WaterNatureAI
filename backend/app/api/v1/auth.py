"""인증 라우터 (FR-001·002). 상세: docs/04-architecture/auth-onboarding.md §8.

리프레시 토큰은 **httpOnly 쿠키**로만 주고받는다(XSS 탈취 차단). 응답 본문에는
access 토큰만 반환하며, 클라이언트는 access를 메모리에 보관하고 Authorization 헤더로
인증한다 → API는 헤더 인증이라 CSRF 표면이 최소. 쿠키는 `/api/v1/auth` 경로로 한정.
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status

from app.api.deps import DbSession
from app.api.ratelimit import rate_limit
from app.core.config import settings
from app.schemas.auth import AccessTokenOut, LoginIn, RegisterIn
from app.services import auth_service

router = APIRouter()

_COOKIE_PATH = f"{settings.api_v1_prefix}/auth"
_REFRESH_COOKIE = settings.refresh_cookie_name


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=_REFRESH_COOKIE,
        value=refresh_token,
        max_age=settings.jwt_refresh_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path=_COOKIE_PATH,
    )


def _clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(
        key=_REFRESH_COOKIE,
        path=_COOKIE_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


@router.post(
    "/register",
    response_model=AccessTokenOut,
    status_code=201,
    dependencies=[Depends(rate_limit("register", limit=5, window_sec=60))],
)
def register(body: RegisterIn, response: Response, db: DbSession) -> AccessTokenOut:
    tokens = auth_service.register(
        db, email=body.email, password=body.password, company_name=body.company_name
    )
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessTokenOut(access_token=tokens.access_token)


@router.post(
    "/login",
    response_model=AccessTokenOut,
    dependencies=[Depends(rate_limit("login", limit=10, window_sec=60))],
)
def login(body: LoginIn, response: Response, db: DbSession) -> AccessTokenOut:
    tokens = auth_service.login(db, email=body.email, password=body.password)
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessTokenOut(access_token=tokens.access_token)


@router.post(
    "/refresh",
    response_model=AccessTokenOut,
    dependencies=[Depends(rate_limit("refresh", limit=30, window_sec=60))],
)
def refresh(
    response: Response,
    db: DbSession,
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> AccessTokenOut:
    if not refresh_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing refresh token")
    tokens = auth_service.refresh(db, refresh_token=refresh_token)
    _set_refresh_cookie(response, tokens.refresh_token)  # 회전된 새 토큰으로 갱신
    return AccessTokenOut(access_token=tokens.access_token)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    db: DbSession,
    refresh_token: str | None = Cookie(default=None, alias=_REFRESH_COOKIE),
) -> None:
    if refresh_token:
        auth_service.logout(db, refresh_token=refresh_token)
    _clear_refresh_cookie(response)
