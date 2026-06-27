# -*- coding: utf-8 -*-
"""NTIS 15074634 라이브 프로브 — envelope/필드명/승인상태 확인.

endpoint: {ntis_base_url}/businessAnnouncMentList
키: settings.ntis_service_key → narajangter_service_key 폴백 (Decoding 키 via params).
returnType json/xml 모두 시도.
"""
from __future__ import annotations

import io
import json
import sys

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.core.config import settings

KEY = settings.ntis_service_key or settings.narajangter_service_key
BASE = f"{settings.ntis_base_url}/businessAnnouncMentList"
print(f"endpoint: {BASE}")
print(f"key set: {bool(KEY)} (len={len(KEY)})\n")


def probe(label: str, params: dict) -> None:
    print(f"\n===== {label} =====")
    print("params:", {k: (v if k != 'serviceKey' else '<KEY>') for k, v in params.items()})
    try:
        r = httpx.get(BASE, params=params, timeout=30)
    except Exception as e:  # noqa: BLE001
        print("REQUEST ERROR:", repr(e))
        return
    print(f"HTTP {r.status_code} | content-type: {r.headers.get('content-type')}")
    body = r.text
    # JSON 파싱 시도
    try:
        data = r.json()
        print("JSON keys (top):", list(data.keys()) if isinstance(data, dict) else type(data))
        print(json.dumps(data, ensure_ascii=False, indent=2)[:2200])
    except Exception:  # noqa: BLE001
        print("RAW (non-JSON) first 2200 chars:")
        print(body[:2200])


# 1) returnType=json (소문자 serviceKey, Decoding 키)
probe("1 returnType=json", {
    "serviceKey": KEY, "pageNo": 1, "numOfRows": 3, "returnType": "json",
})
# 2) type=json (일부 엔드포인트는 returnType 대신 type)
probe("2 type=json", {
    "serviceKey": KEY, "pageNo": 1, "numOfRows": 3, "type": "json",
})
# 3) 파라미터 없이(기본 XML)
probe("3 default(no returnType)", {
    "serviceKey": KEY, "pageNo": 1, "numOfRows": 3,
})
