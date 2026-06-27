# -*- coding: utf-8 -*-
"""FR-004 데모/테스트용 PDF 생성기 (reportlab, 한글 CID 폰트).

생성물:
  - tests/fixtures/sample_brochure.pdf : 단위/통합 테스트용 소형 회사소개서.
  - scripts/fixtures/waternature_brochure.pdf : WaterNature 라이브 데모용 회사소개서.

reportlab은 런타임 의존성이 아님(픽스처 1회 생성용). 생성 후 pypdf 추출로 검증 출력.
"""
from __future__ import annotations

import io
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

pdfmetrics.registerFont(UnicodeCIDFont("HYSMyeongJo-Medium"))
FONT = "HYSMyeongJo-Medium"
W, H = A4
LEFT = 50
TOP = H - 60
LINE = 19


def _draw(c: canvas.Canvas, blocks: list[tuple[str, int]]) -> None:
    """(텍스트, 폰트크기) 블록 리스트를 페이지에 흘려쓰기. 자동 개행/개페이지."""
    y = TOP
    for text, size in blocks:
        if y < 70:
            c.showPage()
            y = TOP
        c.setFont(FONT, size)
        c.drawString(LEFT, y, text)
        y -= LINE + (size - 11)


def build(path: str, blocks: list[tuple[str, int]]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    c = canvas.Canvas(path, pagesize=A4)
    _draw(c, blocks)
    c.save()

    # 검증: pypdf 추출
    from pypdf import PdfReader

    reader = PdfReader(path)
    text = "\n".join((p.extract_text() or "") for p in reader.pages)
    size_kb = os.path.getsize(path) / 1024
    print(f"\n=== {path} ===")
    print(f"pages={len(reader.pages)} size={size_kb:.1f}KB extracted_chars={len(text)}")
    print("extract preview:", " ".join(text.split())[:140])


# ── 테스트 픽스처 (작게) ─────────────────────────────────────────────────────
SAMPLE = [
    ("주식회사 샘플테크 회사소개서", 16),
    ("", 11),
    ("회사명: 주식회사 샘플테크", 11),
    ("업종: 소프트웨어 개발", 11),
    ("주요 서비스: 클라우드 구축, 데이터 분석 플랫폼, AI 챗봇", 11),
    ("보유 기술: Python, AWS, Kubernetes, PostgreSQL", 11),
    ("주요 고객: 공공기관, 중소기업", 11),
    ("보유 인증: ISO 9001, GS인증, 기업부설연구소", 11),
    ("수행 실적: 2024년 OO시 데이터 플랫폼 구축", 11),
]

# ── WaterNature 데모용 회사소개서 (풍부하게) ─────────────────────────────────
WATERNATURE = [
    ("WaterNature 회사소개서", 18),
    ("물과 자연을 잇는 스마트 수처리 기술", 12),
    ("", 11),
    ("1. 회사 개요", 14),
    ("회사명: 주식회사 워터네이처 (WaterNature Co., Ltd.)", 11),
    ("설립: 2017년 / 본사: 대전광역시 유성구 / 사업범위: 전국", 11),
    ("WaterNature는 멤브레인 기반 고도 수처리와 IoT 수질 모니터링을 결합한", 11),
    ("스마트 물환경 솔루션 전문기업입니다. 깨끗한 물 공급과 폐수 재이용을 통해", 11),
    ("지속가능한 물순환 사회를 만들어갑니다.", 11),
    ("", 11),
    ("2. 핵심 사업영역", 14),
    ("- 스마트 정수처리: 막여과(UF/RO) 기반 정수장 고도처리 시스템", 11),
    ("- IoT 수질 모니터링: 실시간 수질 센서 네트워크 및 원격관제 플랫폼", 11),
    ("- 하·폐수 재이용: 산업폐수 재이용 플랜트 설계·시공·운영", 11),
    ("- AI 수질예측: 머신러닝 기반 수질 이상 예측 및 약품 투입 최적화", 11),
    ("- 스마트 상수도: 관망 누수 감지 및 수압 최적화 관리 시스템", 11),
    ("", 11),
    ("3. 보유 기술 및 R&D", 14),
    ("- 저오염 멤브레인 모듈 설계 및 막오염(파울링) 저감 기술", 11),
    ("- 저전력 IoT 수질 센서(탁도·pH·잔류염소·TOC) 및 LoRa 통신", 11),
    ("- AI 기반 수질 예측 알고리즘 및 디지털 트윈 시뮬레이션", 11),
    ("- 기업부설연구소 운영, 환경부 환경신기술(NET) 인증 보유 기술", 11),
    ("", 11),
    ("4. 주요 수행실적", 14),
    ("- 2023년 충청권 OO정수장 고도정수처리(막여과) 시설 구축", 11),
    ("- 2022년 OO산업단지 폐수 재이용 플랜트(일 5,000톤) 설계·시공", 11),
    ("- 2021년 OO시 스마트 상수도 관망관리 시범사업 IoT 구축", 11),
    ("- 한국수자원공사(K-water) 공동연구 및 실증 과제 다수 수행", 11),
    ("", 11),
    ("5. 인증 및 고객", 14),
    ("보유 인증: ISO 9001, ISO 14001, 환경신기술(NET) 인증,", 11),
    ("벤처기업 인증, 이노비즈(Inno-Biz), 기업부설연구소 인정", 11),
    ("주요 고객: 한국수자원공사, 환경부 산하기관, 지방자치단체,", 11),
    ("산업단지 입주기업, 한국환경공단", 11),
    ("", 11),
    ("문의: contact@waternature.co.kr / 042-000-0000", 11),
]


if __name__ == "__main__":
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
    build(os.path.join(base, "tests", "fixtures", "sample_brochure.pdf"), SAMPLE)
    build(os.path.join(base, "scripts", "fixtures", "waternature_brochure.pdf"), WATERNATURE)
    print("\nOK: PDF 생성 완료")
