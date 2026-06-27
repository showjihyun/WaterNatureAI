"""NTIS live 스모크 테스트 (data.go.kr 15074634).

키: settings.ntis_service_key (없으면 narajangter_service_key 폴백).
키가 없으면 pytest.skip. 있으면 첫 페이지 live → item>0 · 필수필드 확인.
⚠️ 미승인/인증 오류 → DataGoKrApiError 잡아 skip 처리 (재시도 없음).

실행 방법:
    backend/.env 에 NTIS_SERVICE_KEY 또는 NARAJANGTER_SERVICE_KEY 설정 후:
        pytest tests/smoke/test_ntis_live.py -v
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.core.config import settings

_has_key = bool(settings.ntis_service_key or settings.narajangter_service_key)

pytestmark = pytest.mark.skipif(
    not _has_key,
    reason="ntis_service_key / narajangter_service_key not set — smoke test skipped",
)


def test_ntis_first_page_live() -> None:
    """첫 페이지 수신 → item > 0 · 필수 필드 존재 확인.

    ⚠️ 미승인 시 DataGoKrApiError → skip 처리.
    TODO(검증): 응답 필드명 실측 후 required_fields 업데이트.
    """
    from app.services.collectors.ntis import NtisCollector
    from app.services.collectors.base import _Window
    from app.services.collectors.client import DataGoKrApiError

    collector = NtisCollector()
    window = _Window(
        begin=datetime.now(timezone.utc) - timedelta(days=30),  # 최근 30일
        end=datetime.now(timezone.utc),
    )

    import httpx  # noqa: PLC0415

    first_page: list[dict] = []
    try:
        for page in collector.iter_pages(window):
            first_page = page
            break  # 첫 페이지만
    except DataGoKrApiError as exc:
        pytest.skip(
            f"NTIS API 미승인/인증 오류 — {exc}. "
            f"활용신청 승인 후 재시도. (비재시도, 즉시 skip)"
        )
    except httpx.HTTPStatusError as exc:
        # 403 Forbidden = 활용신청 미승인 (data.go.kr 표준 동작)
        pytest.skip(
            f"NTIS API HTTP {exc.response.status_code} — 활용신청 미승인 상태. "
            f"승인 후 재시도. (비재시도, 즉시 skip)"
        )

    if not first_page:
        pytest.skip(
            "NTIS 첫 페이지 0건 — 30일 윈도우 내 공고 없거나 API 미승인."
        )

    # 공식 명세(v1.0) 필수 응답 필드: subject(제목)·viewUrl(상세)·pressDt(게시일).
    for item in first_page[:3]:
        assert len(item) > 0, f"item이 비어 있음: {item}"
        required_fields = {"subject", "viewUrl", "pressDt"}
        missing = required_fields - set(item.keys())
        assert not missing, f"필수 필드 누락: {missing} in {item}"

    # 실측 결과 보고용: 첫 아이템의 키 목록 출력
    if first_page:
        first_keys = list(first_page[0].keys())
        print(f"\n[NTIS live] item count={len(first_page)}, fields={first_keys}")
        print(f"[NTIS live] first item sample: {dict(list(first_page[0].items())[:5])}")
