"""FastAPI 공용 의존성 — DB 세션 + 인증(company 스코프 격리)."""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decode_access_token
from app.db.base import get_session

bearer = HTTPBearer(auto_error=True)

DbSession = Annotated[Session, Depends(get_session)]


def get_claims(creds: Annotated[HTTPAuthorizationCredentials, Depends(bearer)]) -> dict:
    try:
        claims = decode_access_token(creds.credentials)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid token") from exc
    if claims.get("type") != "access":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not an access token")
    return claims


def get_current_company_id(claims: Annotated[dict, Depends(get_claims)]) -> uuid.UUID:
    """모든 보호 리소스는 이 company_id로 범위가 제한된다(테넌트 격리)."""
    cid = claims.get("company_id")
    if not cid:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "no company scope")
    return uuid.UUID(cid)


CurrentCompany = Annotated[uuid.UUID, Depends(get_current_company_id)]


def get_admin_email(
    claims: Annotated[dict, Depends(get_claims)], db: DbSession
) -> str:
    """플랫폼 집계(North Star) 지표 접근 게이트 — settings.admin_emails 의 이메일만 허용."""
    admins = {e.strip().lower() for e in settings.admin_emails.split(",") if e.strip()}
    if not admins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "운영 지표가 비활성화되어 있습니다.")
    from app.db.models.accounts import User  # noqa: PLC0415

    user_id = claims.get("sub")
    user = db.get(User, uuid.UUID(user_id)) if user_id else None
    if not user or (user.email or "").lower() not in admins:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "운영자 전용 지표입니다.")
    return user.email


CurrentAdmin = Annotated[str, Depends(get_admin_email)]
