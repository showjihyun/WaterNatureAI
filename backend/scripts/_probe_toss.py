# -*- coding: utf-8 -*-
"""Toss 테스트 시크릿 키 인증 확인 — 빌링 발급 엔드포인트에 더미 authKey로 호출.

유효 키: 더미 authKey라 비즈니스 오류(NOT_FOUND/AUTHKEY 등) → 키 인증은 통과.
무효 키: 401 UNAUTHORIZED_KEY.
"""
from __future__ import annotations

import base64
import io
import os
import sys

import httpx

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ISSUE = "https://api.tosspayments.com/v1/billing/authorizations/issue"

# 키는 하드코딩하지 않고 환경변수로 주입한다(시크릿 레포 유입 방지).
#   TOSS_PROBE_KEYS="label1=key1,label2=key2" python scripts/_probe_toss.py
_raw = os.environ.get("TOSS_PROBE_KEYS", "")
CANDIDATES = [
    (kv.split("=", 1)[0].strip(), kv.split("=", 1)[1].strip())
    for kv in _raw.split(",")
    if "=" in kv
]
if not CANDIDATES:
    print("TOSS_PROBE_KEYS 환경변수에 'label=key[,label=key]' 형식으로 키를 주입하세요.")
    raise SystemExit(0)


def probe(label: str, secret: str) -> None:
    token = base64.b64encode(f"{secret}:".encode()).decode()
    try:
        r = httpx.post(
            ISSUE,
            headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"},
            json={"authKey": "dummy_auth_key", "customerKey": "cust_probe_1"},
            timeout=20,
        )
    except Exception as e:  # noqa: BLE001
        print(f"[{label}] ERR {e!r}")
        return
    code = ""
    try:
        code = str(r.json().get("code", ""))
    except Exception:  # noqa: BLE001
        pass
    verdict = "KEY-INVALID" if code == "UNAUTHORIZED_KEY" else "KEY-OK(인증통과)"
    print(f"[{label}] HTTP {r.status_code} code={code} → {verdict}")
    print("   body:", r.text[:160])


for label, key in CANDIDATES:
    probe(label, key)
