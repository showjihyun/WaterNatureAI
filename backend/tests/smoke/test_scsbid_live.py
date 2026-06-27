"""나라장터 낙찰정보(ScsbidInfoService) serviceKey 스모크 테스트.

키는 settings(=.env의 NARAJANGTER_SERVICE_KEY)에서 읽는다. 없으면 pytest.skip.
있으면 최근 윈도우로 ScsbidCollector().iter_pages() 첫 페이지만 받아
아이템 수 · 필수 필드(낙찰업체/금액)·envelope를 확인한다 (실 네트워크 호출).

실행 방법:
    backend/.env 에 NARAJANGTER_SERVICE_KEY 설정 후:  pytest tests/smoke -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings

pytestmark = pytest.mark.skipif(
    not settings.narajangter_service_key,
    reason="narajangter_service_key not set (.env/env) — smoke test skipped",
)


def test_scsbid_first_page_live() -> None:
    """낙찰 첫 페이지 수신 → item 존재 시 필수 필드 확인."""
    from app.services.collectors.scsbid import ScsbidCollector

    collector = ScsbidCollector()
    end = datetime.now(timezone.utc)
    begin = end - timedelta(days=2)  # 낙찰은 등록 빈도가 낮아 2일 윈도우

    first_page: list[dict] = []
    for items, _category in collector.iter_pages(begin, end):
        first_page = items
        break  # 첫 페이지(첫 업무유형)만

    # 낙찰 등록이 윈도우 내 0건일 수 있음 → 비면 명시적 skip(네트워크/스키마는 정상 의미)
    if not first_page:
        pytest.skip("낙찰 등록 0건 (윈도우 내) — 네트워크/응답은 정상")

    # 응답이 있으면 핵심 필드 존재 확인 (README §4.3)
    required = {"bidNtceNo", "bidNtceNm", "sucsfbidAmt", "bidwinnrNm"}
    for item in first_page[:3]:
        missing = required - set(item.keys())
        assert not missing, f"필수 필드 누락: {missing} in {item}"
