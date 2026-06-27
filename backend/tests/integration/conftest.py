"""통합 테스트 공용 픽스처 — Alembic 마이그레이션 기반 스키마.

- TEST_DATABASE_URL 없으면 통합 테스트 전체 skip.
- engine: settings.database_url 을 TEST_DATABASE_URL 로 오버라이드 후
  `alembic upgrade head` 로 실제 운영 스키마 생성(시드·부분 인덱스·sweep 함수 포함).
  teardown은 `downgrade base`(왕복 검증) + 잔여 alembic_version 정리.
- db_session / session_factory: 테스트마다 트랜잭션 롤백으로 격리.

PostgreSQL 전용(JSONB/UUID/ENUM). SQLite 불가.
seed(sources 5종: narajangter/narajangter_scsbid/bizinfo/kstartup/ntis, plans)는
마이그레이션 0001 이 담당 — 테스트가 수동 seed 하지 않는다(단일 진실원천).

실행:
    TEST_DATABASE_URL="postgresql+psycopg://bizradar:bizradar@localhost:5433/bizradar_test" \
        pytest tests/integration -v
"""
from __future__ import annotations

import os
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Callable
from unittest.mock import MagicMock

import pytest

# ── embedding.tasks stub ───────────────────────────────────────────────────
#    collector.run()이 지연 import 하는 embedding.tasks 의 .delay 를 patch 가능하게
#    app import 전 주입(Celery/임베딩 풀스택 로드 회피). 벡터는 pgvector라 별도 stub 불필요.
#    provider는 voyageai 설치 + lazy import라 stub하지 않음(단위 테스트와 충돌 방지).
_embed_stub = types.ModuleType("app.services.embedding.tasks")
_embed_stub.embed_opportunity = MagicMock(name="embed_opportunity_stub")  # type: ignore[attr-defined]
sys.modules.setdefault("app.services.embedding.tasks", _embed_stub)

# ── skip 조건 ─────────────────────────────────────────────────────────────
TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "")

# 통합 디렉터리 전체에 skip 적용 (collection 시점).
collect_ignore: list[str] = []
if not TEST_DB_URL:
    # 개별 모듈의 pytestmark 로도 skip 되지만, 명시적 가드를 한 곳에 둔다.
    pass


def _alembic_config():
    """backend/ 기준 절대경로로 Alembic Config 구성."""
    from alembic.config import Config  # noqa: PLC0415

    backend_root = Path(__file__).resolve().parents[2]  # tests/integration/conftest.py → backend/
    cfg = Config(str(backend_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend_root / "alembic"))
    return cfg


@pytest.fixture(scope="session")
def engine():
    """마이그레이션으로 생성된 실 스키마 엔진. 세션당 1회 upgrade/downgrade."""
    if not TEST_DB_URL:
        pytest.skip("TEST_DATABASE_URL not set")

    from alembic import command  # noqa: PLC0415
    from sqlalchemy import create_engine, text  # noqa: PLC0415

    # env.py가 settings.database_url 을 읽으므로 그 값을 테스트 DB로 오버라이드.
    from app.core.config import settings  # noqa: PLC0415
    settings.database_url = TEST_DB_URL

    eng = create_engine(TEST_DB_URL, pool_pre_ping=True, future=True)

    # 클린 슬레이트(이전 실패 잔여 정리) 후 head 까지 마이그레이션.
    with eng.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    cfg = _alembic_config()
    command.upgrade(cfg, "head")

    yield eng

    # 왕복 검증 겸 정리: downgrade base 후 alembic_version 도 제거.
    command.downgrade(cfg, "base")
    with eng.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
    eng.dispose()


@pytest.fixture()
def db_session(engine) -> Iterator:
    """각 테스트를 트랜잭션으로 감싸 롤백 → 테스트 간 데이터 격리."""
    from sqlalchemy.orm import Session  # noqa: PLC0415

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture()
def session_factory(db_session) -> Callable:
    """collector 주입용 — 항상 동일 db_session 반환(트랜잭션 공유)."""
    def _factory():
        return db_session
    return _factory
