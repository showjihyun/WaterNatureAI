"""SQLAlchemy 2.0 선언적 Base + 세션 팩토리.

모델 정본: docs/04-architecture/db-schema-opportunities.md (마이그레이션 0001~0009).
engine/SessionLocal은 첫 사용 시 생성(lazy) → 단위 테스트에서 psycopg 없이도 import 가능.
"""
from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings

_engine: Engine | None = None
_session_local: Any | None = None  # sessionmaker instance


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
    return _engine


def _get_session_local():
    global _session_local
    if _session_local is None:
        _session_local = sessionmaker(
            bind=_get_engine(), autoflush=False, expire_on_commit=False
        )
    return _session_local


def SessionLocal() -> Session:
    """세션 팩토리 호출 인터페이스. sessionmaker()처럼 사용."""
    return _get_session_local()()


class Base(DeclarativeBase):
    """모든 ORM 모델의 베이스."""


def get_session() -> Iterator[Session]:
    """FastAPI 의존성용 세션 제너레이터."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 하위 호환: engine 접근자 (Alembic/마이그레이션에서 사용)
def get_engine() -> Engine:
    return _get_engine()
