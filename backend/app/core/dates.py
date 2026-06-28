"""KST(Asia/Seoul) 날짜 유틸. 운영 tz가 KST이므로 D-day/오늘 경계는 KST 기준으로 계산.

UTC 날짜로 빼면 KST 자정~09시 구간에서 하루 어긋난다(예: KST 06/28 02:00은 UTC 06/27).
모든 d_day·'오늘'은 이 모듈의 KST 기준을 쓴다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def kst_today() -> date:
    """오늘 날짜(KST)."""
    return datetime.now(KST).date()
