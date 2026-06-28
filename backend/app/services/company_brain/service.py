"""Company Brain — 프로필+문서 → Company Context 생성. 정본: company-brain.md.

스키마는 매칭 가중치와 1:1(technologies↔기술, track_records↔실적, customers↔고객,
industry↔산업, regions↔지역). content_hash 변경 시 재임베딩+재매칭.

FR-004 파일파싱(PDF/DOCX/PPTX 추출·OCR)은 범위 밖 — 무거운 의존성(pypdf 등).
document_text 인자로 사전 추출된 텍스트를 받거나, 프로필만으로 Context 생성.
TODO(후속): FR-004 파일파싱 — extract_document Celery 태스크(pypdf/python-docx/OCR).
"""
from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import SessionLocal
from app.db.models.accounts import Company
from app.db.models.company_context import CompanyContext

logger = logging.getLogger(__name__)

# Context 추출 스키마(매칭 가중치 1:1) — company-brain.md §3.2
CONTEXT_SCHEMA = {
    "industry": "str", "industries": "list[str]", "technologies": "list[str]",
    "services": "list[str]", "customers": "list[str]", "certifications": "list[str]",
    "regions": "list[str]", "track_records": "list[obj]", "strengths": "list[str]",
    "keywords": "list[str]",
}

# LLM 호출용 JSON Schema (tool_use 강제)
_CONTEXT_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "industry":       {"type": "string"},
        "industries":     {"type": "array",  "items": {"type": "string"}},
        "technologies":   {"type": "array",  "items": {"type": "string"}},
        "services":       {"type": "array",  "items": {"type": "string"}},
        "customers":      {"type": "array",  "items": {"type": "string"}},
        "certifications": {"type": "array",  "items": {"type": "string"}},
        "regions":        {"type": "array",  "items": {"type": "string"}},
        "track_records":  {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title":   {"type": "string"},
                    "year":    {"type": "number"},
                    "client":  {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
        },
        "strengths":      {"type": "array",  "items": {"type": "string"}},
        "keywords":       {"type": "array",  "items": {"type": "string"}},
    },
}


# ── 내부 유틸 ────────────────────────────────────────────────────────────────

def _sha256_norm(*parts: object) -> str:
    """content_hash: sha256(industry|technologies|customers|certifications|strengths|track_records).

    각 파트를 JSON 직렬화(정렬)하여 결합 → sha256 hex.
    """
    serialized = "|".join(
        json.dumps(p, ensure_ascii=False, sort_keys=True) if not isinstance(p, str) else p
        for p in parts
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def _profile_to_text(company: Company) -> str:
    """Company ORM 행 → 자연어 텍스트(LLM 투입용). 온보딩 전 필드 포함."""
    lines = [f"회사명: {company.name}"]
    if company.industry:
        lines.append(f"업종: {company.industry}")
    if company.description:
        lines.append(f"설명: {company.description}")
    if company.region:
        lines.append(f"지역: {company.region}")
    if company.services:
        lines.append(f"주요 서비스/제품: {', '.join(company.services)}")
    if company.technologies:
        lines.append(f"보유 기술: {', '.join(company.technologies)}")
    if company.customers:
        lines.append(f"주요 고객사 유형: {', '.join(company.customers)}")
    if company.certifications:
        lines.append(f"보유 인증: {', '.join(company.certifications)}")
    return "\n".join(lines)


# 공유 상수 — app.services.keywords 에서 임포트 (engine.py 와 DRY)
from app.services.keywords import INDUSTRY_KEYWORDS as _INDUSTRY_KEYWORDS  # noqa: E402
from app.services.keywords import STOPWORDS as _STOPWORDS  # noqa: E402


def _derive_keywords(industry: str, description: str) -> list[str]:
    """industry/description에서 시드 키워드 파생(LLM 없을 때 fallback).

    stopwords(범용 단어)는 제외하여 노이즈 매칭 방지.
    """
    derived: list[str] = []
    source = f"{industry} {description}"
    for key, kws in _INDUSTRY_KEYWORDS.items():
        if key in source:
            # 산업 키워드는 stopwords 필터 없이 추가 (명시적 도메인 용어)
            derived.extend(kws)
    # description 토큰화: 2자 이상 한국어 단어 중 stopwords 제외
    import re  # noqa: PLC0415
    tokens = re.findall(r"[가-힣]{2,}", description or "")
    seen: set[str] = set(derived)
    for t in tokens:
        if t in _STOPWORDS:
            continue
        if t not in seen:
            derived.append(t)
            seen.add(t)
        if len(derived) >= 15:
            break
    return list(dict.fromkeys(derived))[:15]


def _profile_to_context(company: Company) -> dict:
    """LLM 없을 때 Company 프로필 필드 → CONTEXT_SCHEMA 직접 매핑.

    문서 AI 이해 없이 구조화 프로필만으로 Context 생성(규칙 매칭용 최소 필드).
    keywords가 비면 industry/description에서 시드 키워드 파생해 매칭 신호 확보.
    """
    regions: list[str] = [company.region] if company.region else []
    industry: str = company.industry or ""
    description: str = company.description or ""
    technologies = [t.strip() for t in (company.technologies or []) if t and t.strip()]
    services = [s.strip() for s in (company.services or []) if s and s.strip()]
    customers = [c.strip() for c in (company.customers or []) if c and c.strip()]
    certifications = [c.strip() for c in (company.certifications or []) if c and c.strip()]
    keywords = _derive_keywords(industry, description)
    # 온보딩 입력(기술·서비스)도 매칭 키워드에 합류해 매칭 신호 강화
    for extra in technologies + services:
        if extra not in keywords:
            keywords.append(extra)
    return {
        "industry": industry,
        "industries": [industry] if industry else [],
        "technologies": technologies,
        "services": services,
        "customers": customers,
        "certifications": certifications,
        "regions": regions,
        "track_records": [],
        "strengths": [],
        "keywords": keywords[:30],
    }


def _validate_context(context: dict) -> None:
    """최소 검증: industry 또는 technologies 중 하나는 존재해야 함."""
    if not context.get("industry") and not context.get("technologies"):
        raise ValueError(
            f"Context 검증 실패: industry와 technologies 모두 비어있음. keys={list(context.keys())}"
        )


# ── 공개 API ────────────────────────────────────────────────────────────────

def build_company_context(
    company_id: str,
    *,
    document_text: str | None = None,
    db: Session | None = None,
    llm_complete_json: Callable | None = None,
) -> str:
    """프로필 + (선택) 사전추출 텍스트 → LLM 구조화 추출 → company_contexts UPSERT.

    Args:
        company_id:       대상 기업 UUID 문자열.
        document_text:    사전 추출된 문서 텍스트(선택). None이면 프로필만 사용.
                          FR-004 파일파싱은 TODO(후속) — 이 인자로 외부에서 주입.
        db:               주입 세션(테스트용). None이면 SessionLocal() 사용.
        llm_complete_json: LLM 함수. None이면 프로필 직접 매핑(fallback, 문서 AI 이해 없음).

    Returns:
        str: company_contexts.id (upsert된 행 UUID 문자열).

    Side-effects:
        - company_contexts UPSERT (content_hash 변경 시 embedding/matching enqueue).
        - content_hash 변경 시 embed_company_context.delay + matching.run_daily.delay enqueue.
    """
    _own_db = db is None
    _db: Session = db if db is not None else SessionLocal()

    try:
        # ① 기업 프로필 조회
        company = _db.get(Company, uuid.UUID(company_id))
        if company is None:
            raise ValueError(f"Company not found: {company_id}")

        # ② Context 생성: LLM 있으면 AI 추출, 없으면 프로필 직접 매핑(fallback)
        if llm_complete_json is not None:
            profile_text = _profile_to_text(company)
            user_text = profile_text
            if document_text:
                user_text += f"\n\n## 첨부 문서 발췌\n{document_text[:8000]}"

            system_prompt = (
                "당신은 기업 역량 분석 전문가다. "
                "제공된 기업 프로필과 문서에서 정확히 structured_output 도구로 Company Context를 추출하라. "
                "문서에 없는 정보는 빈 리스트/빈 문자열로 두라(환각 금지). "
                "track_records는 확인된 수행실적만 포함하라."
            )
            user_prompt = (
                f"## 기업 정보\n{user_text}\n\n"
                "위 정보를 분석해 structured_output 도구로 Company Context를 추출하라.\n"
                "- industry: 대표 산업 분류(단일 문자열)\n"
                "- industries: 복수 산업 영역 리스트\n"
                "- technologies: 핵심 기술 키워드 리스트\n"
                "- services: 제공 서비스/솔루션 리스트\n"
                "- customers: 주요 고객사/발주처 리스트\n"
                "- certifications: 보유 인증/자격 리스트\n"
                "- regions: 사업 지역 리스트(예: ['서울', '전국'])\n"
                "- track_records: 수행실적 리스트(각 항목: title, year, client, summary)\n"
                "- strengths: 핵심 강점 리스트\n"
                "- keywords: 매칭 보조 키워드 리스트"
            )
            context = llm_complete_json(system_prompt, user_prompt, _CONTEXT_JSON_SCHEMA)
        else:
            # LLM 미설정: 프로필 필드 → context_json 직접 매핑 (문서 AI 이해 없음)
            context = _profile_to_context(company)
            logger.info("build_company_context: LLM 미설정 — 프로필 기반 Context 생성 (company_id=%s)", company_id)

        # ③ 검증
        _validate_context(context)

        # ④ content_hash 산출
        new_hash = _sha256_norm(
            context.get("industry", ""),
            context.get("technologies", []),
            context.get("customers", []),
            context.get("certifications", []),  # 인증도 해시 포함 → 인증만 수정해도 재임베딩·재매칭.
            context.get("strengths", []),
            context.get("track_records", []),
        )

        # ⑤ 기존 company_context 조회 (hash 비교용)
        existing = _db.scalars(
            select(CompanyContext)
            .where(CompanyContext.company_id == uuid.UUID(company_id))
            .order_by(CompanyContext.created_at.desc())
            .limit(1)
        ).first()

        old_hash = existing.content_hash if existing else None
        cc_id: uuid.UUID

        if existing is not None:
            # UPDATE
            existing.context_json = context
            existing.content_hash = new_hash
            _db.flush()
            cc_id = existing.id
        else:
            # INSERT
            cc_id = uuid.uuid4()
            new_cc = CompanyContext(
                id=cc_id,
                company_id=uuid.UUID(company_id),
                context_json=context,
                content_hash=new_hash,
            )
            _db.add(new_cc)
            _db.flush()

        # 워커가 새 company_context 행을 읽을 수 있도록 enqueue 전에 항상 커밋
        # (db 주입 시에도). 미커밋이면 embed_company_context가 행을 못 찾아 no-op.
        _db.commit()

        # ⑥ content_hash 변경 시 재임베딩 + 재매칭 enqueue
        if new_hash != old_hash:
            _enqueue_embed_and_rematch(str(cc_id), company_id)

        return str(cc_id)

    except Exception:
        if _own_db:
            _db.rollback()
        raise
    finally:
        if _own_db:
            _db.close()


def _enqueue_embed_and_rematch(cc_id: str, company_id: str) -> None:
    """재임베딩 → 재매칭을 celery chain으로 enqueue (순서 보장 + 단일 publish).

    embed_company_context 완료 후에만 run_daily가 실행되도록 chain으로 묶는다.
    이유:
    - embed는 최초 e5 모델 로드로 수십 초 걸려, 별개 .delay()면 run_daily가 먼저
      끝나 방금 가입한 회사가 매칭에서 누락된다(다음 daily까지 추천 0).
    - 연속 .delay() 2회는 간헐적으로 앞선 메시지가 유실된다(단일 apply_async로 회피).
    .si()=immutable signature: embed 반환값을 run_daily(인자 0개)에 전달하지 않는다.
    Celery가 없는 테스트 환경에서도 안전하게 동작(예외 흡수).
    """
    try:
        from celery import chain  # noqa: PLC0415

        from app.services.embedding.tasks import embed_company_context  # noqa: PLC0415
        from app.services.matching.tasks import run_daily  # noqa: PLC0415

        # run_daily(company_id=...) → 방금 가입한 기업만 즉시 매칭(전체 run 대기 없이 빠른 활성화).
        chain(
            embed_company_context.si(cc_id),
            run_daily.si(company_id=company_id),
        ).apply_async()
        logger.info("embed→run_daily(single) chain enqueued: cc_id=%s company_id=%s", cc_id, company_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("embed/rematch chain enqueue 실패: %s", exc)
