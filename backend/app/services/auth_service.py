"""인증 서비스 — 가입(회사+관리자), 로그인, refresh 회전, 로그아웃.

정본: docs/04-architecture/auth-onboarding.md §3·§4·§9.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    hash_password,
    hash_refresh,
    new_refresh_token,
    verify_password,
)
from app.db.models.accounts import Company, RefreshToken, User
from app.schemas.auth import TokenOut


def _issue_tokens(db: Session, user: User) -> TokenOut:
    assert user.company_id is not None  # 가입 트랜잭션에서 항상 설정(users N:1 companies)
    access = create_access_token(user_id=user.id, company_id=user.company_id, role=user.role)
    raw, token_hash, expires_at = new_refresh_token()
    db.add(RefreshToken(user_id=user.id, token_hash=token_hash, expires_at=expires_at))
    db.commit()
    return TokenOut(access_token=access, refresh_token=raw)


def register(db: Session, *, email: str, password: str, company_name: str) -> TokenOut:
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "email already exists")
    # 트랜잭션: 회사 → 관리자 user (auth §3)
    company = Company(name=company_name, onboarding_status="profile")
    db.add(company)
    db.flush()
    user = User(
        email=email,
        password_hash=hash_password(password),
        company_id=company.id,
        role="company_admin",
    )
    db.add(user)
    db.flush()
    return _issue_tokens(db, user)


def login(db: Session, *, email: str, password: str) -> TokenOut:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        # 미존재 이메일도 동일한 해시 검증 비용 지불(열거 타이밍 오라클 차단).
        verify_password(DUMMY_PASSWORD_HASH, password)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    if not verify_password(user.password_hash, password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")
    return _issue_tokens(db, user)


# 재사용 탐지 유예창: 동시 새로고침(여러 탭 등)으로 갓 회전된 토큰이 재제출될 수 있어,
# 이 창 안의 재사용은 양성으로 보고 패밀리 폐기를 보류한다. 창을 넘긴 재사용 = 탈취 의심.
_REFRESH_REUSE_GRACE = timedelta(seconds=30)


def refresh(db: Session, *, refresh_token: str) -> TokenOut:
    rec = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh(refresh_token))
    )
    if rec is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")
    now = datetime.now(timezone.utc)

    # 재사용 탐지: 이미 폐기된 토큰을 (유예창 밖에서) 다시 제출 = 탈취 의심 →
    # 해당 사용자의 모든 유효 리프레시 토큰 폐기(전 세션 강제 로그아웃).
    if rec.revoked_at is not None:
        if now - rec.revoked_at > _REFRESH_REUSE_GRACE:
            db.execute(
                update(RefreshToken)
                .where(
                    RefreshToken.user_id == rec.user_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "refresh token reuse detected")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")

    if rec.expires_at < now:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid refresh token")

    rec.revoked_at = now  # 회전
    user = db.get(User, rec.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return _issue_tokens(db, user)


def logout(db: Session, *, refresh_token: str) -> None:
    rec = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh(refresh_token))
    )
    if rec and rec.revoked_at is None:
        rec.revoked_at = datetime.now(timezone.utc)
        db.commit()
