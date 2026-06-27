# -*- coding: utf-8 -*-
"""NTIS 승인 전파 폴링 — 200 되는 즉시 envelope/필드 캡처.

http/https × Encoding(raw)/Decoding(params) 4조합을 매 라운드 시도.
하나라도 200이면 전체 JSON(또는 XML) 출력 후 종료.
"""
from __future__ import annotations

import io
import json
import sys
import time

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from app.core.config import settings

DEC = settings.ntis_service_key or settings.narajangter_service_key
ENC = ("1TBhKBR6pq3IVyBIXeW7J2zWbUvAm34oZ9IF4jArB4GYlfp3T5GnfDi2AT7Min"
       "QoFAFxgz5pY9KPghtTv%2BnQaQ%3D%3D")
PATH = "1721000/msitannouncementinfo/businessAnnouncMentList"


def attempts() -> list[tuple[str, str, dict]]:
    common = {"pageNo": 1, "numOfRows": 5, "returnType": "json"}
    return [
        ("http  DEC params", f"http://apis.data.go.kr/{PATH}", {"serviceKey": DEC, **common}),
        ("https DEC params", f"https://apis.data.go.kr/{PATH}", {"serviceKey": DEC, **common}),
        ("http  ENC raw", f"http://apis.data.go.kr/{PATH}?serviceKey={ENC}&pageNo=1&numOfRows=5&returnType=json", None),
        ("https ENC raw", f"https://apis.data.go.kr/{PATH}?serviceKey={ENC}&pageNo=1&numOfRows=5&returnType=json", None),
    ]


ROUNDS = 6
for r in range(ROUNDS):
    for label, url, params in attempts():
        try:
            resp = httpx.get(url, params=params, timeout=30) if params else httpx.get(url, timeout=30)
        except Exception as e:  # noqa: BLE001
            print(f"r{r} {label}: ERR {e!r}", flush=True)
            continue
        code = resp.status_code
        if code == 200 and "forbidden" not in resp.text[:50].lower():
            print(f"\n*** 200 OK via [{label}] ***", flush=True)
            ct = resp.headers.get("content-type", "")
            print("content-type:", ct)
            try:
                data = resp.json()
                print("top keys:", list(data.keys()) if isinstance(data, dict) else type(data))
                print(json.dumps(data, ensure_ascii=False, indent=2)[:3500])
            except Exception:  # noqa: BLE001
                print("RAW first 3500:")
                print(resp.text[:3500])
            sys.exit(0)
        print(f"r{r} {label}: HTTP {code} {resp.text[:30].strip()!r}", flush=True)
    if r < ROUNDS - 1:
        time.sleep(20)

print("\n아직 403 — 전파 미완(또는 미승인). 잠시 후 재시도 필요.")
