"""나라장터 serviceKey 스모크 테스트.

키는 settings(=.env의 NARAJANGTER_SERVICE_KEY)에서 읽는다. 키가 없으면 pytest.skip.
있으면 1일 윈도우로 NarajangterCollector().iter_pages() 첫 페이지만 받아
아이템 수 > 0 · 필수 필드 존재를 확인한다 (실 네트워크 호출).

실행 방법(둘 다 가능):
    backend/.env 에 NARAJANGTER_SERVICE_KEY 설정 후:  pytest tests/smoke -v
    또는 env 주입:  NARAJANGTER_SERVICE_KEY=<key> pytest tests/smoke -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    not settings.narajangter_service_key,
    reason="narajangter_service_key not set (.env/env) — smoke test skipped",
)


def test_narajangter_first_page_live() -> None:
    """첫 페이지 수신 → item > 0 · 필수 필드 존재 확인."""
    from app.services.collectors.narajangter import NarajangterCollector
    from app.services.collectors.base import _Window

    collector = NarajangterCollector()
    window = _Window(
        begin=datetime.now(timezone.utc) - timedelta(days=1),
        end=datetime.now(timezone.utc),
    )

    first_page: list[dict] = []
    for page in collector.iter_pages(window):
        first_page = page
        break  # 첫 페이지만

    assert len(first_page) > 0, "첫 페이지 아이템이 0개 — API 응답 이상"

    required_fields = {"bidNtceNo", "bidNtceNm", "ntceInsttNm", "bidClseDt"}
    for item in first_page[:3]:  # 상위 3건만 필드 확인
        missing = required_fields - set(item.keys())
        assert not missing, f"필수 필드 누락: {missing} in {item}"
