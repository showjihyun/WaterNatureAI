# -*- coding: utf-8 -*-
"""K-Startup B552735 프로브 — serviceKey 파라미터명 대소문자/형태 전수."""
from __future__ import annotations

import io
import sys

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.core.config import settings

DEC = settings.narajangter_service_key
ENC = ("1TBhKBR6pq3IVyBIXeW7J2zWbUvAm34oZ9IF4jArB4GYlfp3T5GnfDi2AT7Min"
       "QoFAFxgz5pY9KPghtTv%2BnQaQ%3D%3D")
BASE = "https://apis.data.go.kr/B552735/kisedKstartupService01/getAnnouncementInformation01"


def show(label: str, resp: httpx.Response) -> None:
    print(f"\n--- {label}: HTTP {resp.status_code} ({resp.headers.get('content-type')}) ---")
    print(resp.text[:1400])


# 1. ServiceKey (대문자 S) — 문서 표기. Decoding 키 via params.
try:
    show("1 ServiceKey(대문자) params",
         httpx.get(BASE, params={"ServiceKey": DEC, "page": 1, "perPage": 3, "returnType": "json"},
                   timeout=30))
except Exception as e:  # noqa: BLE001
    print("1 ERR:", e)

# 2. ServiceKey (대문자) + Encoding 키 raw URL.
try:
    show("2 ServiceKey(대문자) Encoding raw",
         httpx.get(f"{BASE}?ServiceKey={ENC}&page=1&perPage=3&returnType=json", timeout=30))
except Exception as e:  # noqa: BLE001
    print("2 ERR:", e)

# 3. serviceKey (소문자) + Encoding 키 raw URL (대조군).
try:
    show("3 serviceKey(소문자) Encoding raw",
         httpx.get(f"{BASE}?serviceKey={ENC}&page=1&perPage=3&returnType=json", timeout=30))
except Exception as e:  # noqa: BLE001
    print("3 ERR:", e)
