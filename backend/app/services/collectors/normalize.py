"""정규화 유틸 — 날짜(KST)·예산·해시·상태.

정본: collector-narajangter.md §6.
검증(2026-06, 15129394 BidPublicInfoService):
  · 응답 일시(bidNtceDt/bidClseDt) = 'yyyy-MM-dd HH:mm:ss' (예 "2026-06-16 18:00:00")
  · 요청 파라미터(inqryBgnDt/inqryEndDt) = 'yyyyMMddHHmm' 12자리
  → 응답·요청 포맷이 다르므로 parse_kst는 두 포맷 모두 수용.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

KST = ZoneInfo("Asia/Seoul")

# 시도 순서 중요: 더 긴 포맷을 먼저(짧은 것이 부분 매치하지 않도록)
# 검증 완료:
#   · 15129394 응답 일시(bidNtceDt/bidClseDt) = 'yyyy-MM-dd HH:mm:ss'  ← 주 경로
#   · 요청 파라미터(inqryBgnDt/inqryEndDt)는 'yyyyMMddHHmm' 12자리(요청 인코딩은 별도)
#   12자리 포맷도 수용(요청 echo·타 소스·15058815 변형 흡수).
_DATE_FORMATS = (
    "%Y-%m-%d %H:%M:%S",  # "2026-06-16 18:00:00"  ← 15129394 응답 일시 표준
    "%Y-%m-%d %H:%M",     # "2026-06-16 18:00"
    "%Y.%m.%d %H:%M:%S",  # "2026.06.16 18:00:00"  (기업마당 등 점 표기)
    "%Y.%m.%d %H:%M",     # "2026.06.16 18:00"
    "%Y%m%d%H%M",         # "202606161800"  (요청 파라미터 포맷·타 소스 호환)
    "%Y-%m-%d",           # "2026-06-16"
    "%Y.%m.%d",           # "2026.06.16"  (기업마당 reqstBeginEndDe 점 표기)
    "%Y%m%d",             # "20260616"
)


def parse_kst(value: str | None) -> datetime | None:
    """공고 일시 문자열을 KST tz-aware datetime으로 파싱. 실패 시 None(레코드 보존).

    지원 포맷: "2026-06-16 18:00:00"(15129394 응답 표준), "202606161800"(요청·호환) 등.
    (collector-narajangter.md §6. 15129394 응답은 'yyyy-MM-dd HH:mm:ss' 검증 완료.)

    비정형 일시: 나라장터(15129394)는 전자입찰 엔진상 마감일시가 고정 timestamp이며
    '상시'/'예산소진시' 같은 자유텍스트는 들어오지 않음(검증 완료). 미설정 시 빈값/None만
    발생 → 빈값·미지원 포맷은 None 반환(레코드 보존). 그랜트성('상시' 등) 비정형 마감은
    기업마당/K-Startup의 reqstBeginEndDe 파서가 별도 처리(collector-base-bizinfo §218).
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=KST)
        except ValueError:
            continue
    logger.warning("parse_kst: 파싱 실패 (지원 포맷 없음) — value=%r", value)
    return None


# 한글 금액 단위 (큰 단위부터). '억'·'만'은 곱셈 누적, 그 외 한글은 무시.
_WON_UNITS: tuple[tuple[str, int], ...] = (("억", 100_000_000), ("만", 10_000))


def parse_won(value: str | None) -> int | None:
    """예산 문자열에서 금액(원)을 추출.

    검증(15129394): presmptPrce/asignBdgtAmt는 숫자 문자열(예 "350000000")로 옴 →
    기본 경로는 콤마·'원' 제거 후 숫자 추출. 단, 상세/타 소스의 '억/만' 한글 표기도 흡수.

    예: "350,000,000원" → 350000000
        "350000000"     → 350000000
        "15억"          → 1500000000
        "3억 5,000만원"  → 350000000
        "5,000만"       → 50000000
        ""·None·숫자없음 → None
    """
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None

    # 한글 단위('억'/'만')가 있으면 단위 분해 합산
    if any(u in s for u in ("억", "만")):
        total = 0
        rest = s
        matched = False
        for unit, mult in _WON_UNITS:
            if unit in rest:
                head, rest = rest.split(unit, 1)
                head_digits = re.sub(r"[^0-9]", "", head)
                if head_digits:
                    total += int(head_digits) * mult
                    matched = True
        # 단위 뒤 잔여 숫자(예 "...만 3000원")는 원 단위로 가산
        tail_digits = re.sub(r"[^0-9]", "", rest)
        if tail_digits:
            total += int(tail_digits)
            matched = True
        return total if matched else None

    digits = re.sub(r"[^0-9]", "", s)
    return int(digits) if digits else None


def sha256_norm(*parts: object) -> str:
    """핵심 필드를 정규화(공백 축약·소문자·strip) 후 '|' 결합 SHA-256(hex).

    - None은 빈 문자열로 처리
    - 공백 연속은 단일 스페이스로 축약
    - 대소문자 무시 (소문자 변환)

    입력 순서가 해시에 영향을 주므로, 호출 시 항상 같은 순서로 전달해야 함.
    (collector-narajangter.md §6: title|agency|deadline|budget_amount|description)
    """
    norm: list[str] = []
    for p in parts:
        s = "" if p is None else str(p)
        norm.append(re.sub(r"\s+", " ", s).strip().lower())
    return hashlib.sha256("|".join(norm).encode()).hexdigest()


def derive_status(deadline: datetime | None) -> str:
    """마감 일시 기준으로 open/closed/unknown 결정.

    deadline이 None이면 unknown.
    deadline < now(UTC) 이면 closed, 그 외 open.
    """
    if deadline is None:
        return "unknown"
    return "closed" if deadline < datetime.now(timezone.utc) else "open"


# 신청기간 범위 구분자.
#   · 물결(~/〜/～): 날짜에 안 나타나므로 공백 없이도 구분자로 인정.
#   · 대시(-/–/—)·'부터': ISO 날짜의 하이픈(2026-06-01)과 충돌 → 양쪽 공백 있을 때만 구분자.
_PERIOD_SEP = re.compile(r"\s*[~〜～]\s*|\s+(?:[-–—]|부터)\s+")
# 비정형 신청기간 키워드 — 마감 없음/날짜 아님 처리.
# 기업마당 라이브 실측 비정형 값 기반(예산 소진시까지/상시 접수/모집 완료시/
# 선착순 접수/세부사업별 상이/수시 모집/차수별 상이/수시 접수).
_ROLLING_KEYWORDS = (
    "상시", "예산", "소진", "수시", "연중", "별도",
    "선착순", "모집", "완료", "상이", "차수", "미정", "추후",
)


def split_reqst_period(value: str | None) -> tuple[datetime | None, datetime | None]:
    """기업마당 reqstBeginEndDe(신청기간 범위 문자열)를 (시작, 종료)로 분리.

    정본: collector-base-bizinfo.md §3.3·§5.
    예:
      "20260601 ~ 20260630"        → (2026-06-01, 2026-06-30)
      "2026.06.01~2026.06.30"      → (2026-06-01, 2026-06-30)
      "2026-06-01 ~ 2026-06-30"    → (2026-06-01, 2026-06-30)
      "20260630"(단일)             → (None, 2026-06-30)  ← 마감만
      "상시"·"예산소진시까지"·""·None → (None, None)     ← 비정형/없음

    날짜 파싱은 parse_kst 재사용(KST tz-aware). 파싱 실패분은 None(레코드 보존).
    """
    if not value:
        return (None, None)
    s = str(value).strip()
    if not s:
        return (None, None)

    # 비정형(상시 등) → 마감 없음
    if any(kw in s for kw in _ROLLING_KEYWORDS):
        logger.debug("split_reqst_period: 비정형(상시류) — value=%r", value)
        return (None, None)

    parts = [p.strip() for p in _PERIOD_SEP.split(s) if p.strip()]

    if len(parts) >= 2:
        start = parse_kst(parts[0])
        end = parse_kst(parts[-1])
        return (start, end)

    if len(parts) == 1:
        # 단일 날짜 → 마감(종료)으로 간주, 시작은 미상
        end = parse_kst(parts[0])
        return (None, end)

    return (None, None)
