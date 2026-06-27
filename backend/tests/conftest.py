"""공유 픽스처 — 나라장터 raw JSON envelope 샘플 포함.

단위 테스트: DB 불필요 픽스처만.
통합 테스트: TEST_DATABASE_URL 없으면 skip.
"""
from __future__ import annotations

import pytest


# ── 나라장터 현실적 응답 픽스처 ─────────────────────────────────────────

@pytest.fixture()
def narajangter_item_thng() -> dict:
    """물품 입찰공고 raw item (단일 dict, _category 미포함).

    필드명/포맷: 15129394 BidPublicInfoService 검증 기준.
    일시는 ISO형도 parse_kst가 흡수(15058815 호환) — 여기선 ISO로 dual-format 검증.
    """
    return {
        "bidNtceNo": "20240600123",
        "bidNtceOrd": "000",
        "bidNtceNm": "2024년 사무용 PC 구매 입찰공고",
        "ntceInsttNm": "서울특별시 강남구청",
        "dminsttNm": "강남구청 총무과",
        "bidNtceDt": "2026-06-16 10:00:00",
        "bidClseDt": "2026-07-10 18:00:00",
        "presmptPrce": "350000000",          # 15129394: 숫자 문자열(콤마 없음)
        "asignBdgtAmt": "360000000",
        "bidNtceDtlUrl": "https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=20240600123",
    }


@pytest.fixture()
def narajangter_item_servc() -> dict:
    """용역 입찰공고 raw item (15129394 응답 포맷: 'yyyy-MM-dd HH:mm:ss')."""
    return {
        "bidNtceNo": "20240600456",
        "bidNtceOrd": "001",               # 정정 차수 1
        "bidNtceNm": "청사 보안경비 용역",
        "ntceInsttNm": "국토교통부",
        "dminsttNm": None,
        "bidNtceDt": "2026-06-17 12:00:00",   # 검증: 응답 일시는 대시/콜론 포맷
        "bidClseDt": "2026-07-05 18:00:00",
        "presmptPrce": None,                  # 추정가격 미제공 → asignBdgtAmt 폴백
        "asignBdgtAmt": "120000000",
        "bidNtceDtlUrl": "https://www.g2b.go.kr/pt/menu/selectSubFrame.do?bidNtceNo=20240600456",
    }


@pytest.fixture()
def narajangter_item_closed() -> dict:
    """마감된 입찰공고 (deadline이 과거)."""
    return {
        "bidNtceNo": "20230100001",
        "bidNtceOrd": "000",
        "bidNtceNm": "2023년 청소 용역 입찰",
        "ntceInsttNm": "경기도 수원시청",
        "dminsttNm": None,
        "bidNtceDt": "2023-01-01 09:00:00",
        "bidClseDt": "2023-01-20 18:00:00",  # 과거 → closed
        "presmptPrce": "50,000,000원",
        "asignBdgtAmt": None,
        "bidNtceDtlUrl": None,
    }


@pytest.fixture()
def narajangter_envelope_multi(
    narajangter_item_thng, narajangter_item_servc
) -> dict:
    """다건 응답 envelope (totalCount=2, numOfRows=100, pageNo=1)."""
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "items": [narajangter_item_thng, narajangter_item_servc],
                "totalCount": 2,
                "numOfRows": 100,
                "pageNo": 1,
            },
        }
    }


@pytest.fixture()
def narajangter_envelope_nodata() -> dict:
    """데이터 없음 응답 (NODATA_CODE='03')."""
    return {
        "response": {
            "header": {"resultCode": "03", "resultMsg": "NODATA_ERROR"},
            "body": {
                "items": "",
                "totalCount": 0,
                "numOfRows": 100,
                "pageNo": 1,
            },
        }
    }


@pytest.fixture()
def narajangter_envelope_auth_error() -> dict:
    """쿼터 초과 오류 응답 (resultCode='22', 비NODATA·비재시도).

    표준코드 22 = LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR.
    """
    return {
        "response": {
            "header": {
                "resultCode": "22",
                "resultMsg": "LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR",
            },
            "body": {},
        }
    }


@pytest.fixture()
def narajangter_envelope_nested_item(narajangter_item_thng) -> dict:
    """단건 nested items.item dict 형태."""
    return {
        "response": {
            "header": {"resultCode": "00", "resultMsg": "NORMAL SERVICE."},
            "body": {
                "items": {"item": narajangter_item_thng},
                "totalCount": 1,
                "numOfRows": 100,
                "pageNo": 1,
            },
        }
    }
