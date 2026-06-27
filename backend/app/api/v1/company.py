"""회사 프로필/온보딩 라우터 (FR-003·FR-004·company-brain). 정본: auth-onboarding.md, company-brain.md.

온보딩 흐름: profile → document → brain → ready (companies.onboarding_status).
- GET  /company/profile   : 현재 회사 프로필.
- PUT  /company/profile   : 전달 필드 부분 수정. status='profile'이면 'document'로 전이.
- POST /company/documents : 회사소개서 PDF 파싱 → document_text 저장(FR-004). status 'document'→'brain'.
- POST /company/brain     : build_company_context(document_text 주입) → status='ready'.

모든 엔드포인트는 CurrentCompany 스코프(테넌트 격리).
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, UploadFile, status
from fastapi.concurrency import run_in_threadpool

from app.api.deps import CurrentCompany, DbSession
from app.db.models.accounts import Company
from app.schemas.company import CompanyProfileIn, CompanyProfileOut
from app.services.company_brain.service import build_company_context
from app.services.documents.extractor import (
    MAX_UPLOAD_BYTES,
    DocumentError,
    DocumentTooLargeError,
    EmptyDocumentError,
    UnsupportedDocumentError,
    extract_document,
)
from app.services.llm import resolve_llm_fn

router = APIRouter()


def _get_company(db: DbSession, company_id: CurrentCompany) -> Company:
    company = db.get(Company, company_id)
    if company is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "company not found")
    return company


async def _read_limited(file: UploadFile, limit: int) -> bytes:
    """업로드 본문을 limit까지만 청크로 읽고 초과 시 즉시 413.

    이전엔 `await file.read()`로 전량을 메모리에 적재한 뒤에야 크기를 검사해서,
    대용량 업로드로 워커 메모리를 고갈시킬 수 있었다(인증돼도 DoS). 여기서 상한을
    넘는 순간 중단해 메모리 사용을 limit 수준으로 묶는다.
    """
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1MB씩
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                f"파일이 너무 큽니다(최대 {limit // 1024 // 1024}MB).",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.get("/profile", response_model=CompanyProfileOut)
def get_profile(company_id: CurrentCompany, db: DbSession) -> Company:
    return _get_company(db, company_id)


@router.put("/profile", response_model=CompanyProfileOut)
def update_profile(body: CompanyProfileIn, company_id: CurrentCompany, db: DbSession) -> Company:
    """전달된 필드만 반영(부분 수정). 프로필 입력 완료 시 'document' 단계로 전이."""
    company = _get_company(db, company_id)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(company, field, value)
    if company.onboarding_status == "profile":
        company.onboarding_status = "document"
    db.commit()
    db.refresh(company)
    return company


@router.post("/brain")
def build_brain(company_id: CurrentCompany, db: DbSession) -> dict:
    """프로필 + 회사소개서(document_text) → Company Context 생성 후 온보딩 완료('ready').

    활성 LLM 공급자(설정 UI)가 있으면 **LLM으로 구조화 추출**(기술·서비스·실적·
    고객·강점·키워드), 없으면 프로필 직접 매핑(fallback). 업로드된 회사소개서
    추출 텍스트(company.document_text)가 있으면 LLM 추출 입력에 합류. content_hash
    변경 시 embed/rematch enqueue는 build_company_context 내부에서 처리.
    """
    company = _get_company(db, company_id)
    cc_id = build_company_context(
        str(company_id),
        document_text=company.document_text,
        db=db,
        llm_complete_json=resolve_llm_fn(db),
    )
    company.onboarding_status = "ready"
    db.commit()
    return {"company_context_id": cc_id, "onboarding_status": company.onboarding_status}


@router.post("/documents")
async def upload_document(file: UploadFile, company_id: CurrentCompany, db: DbSession) -> dict:
    """회사소개서 PDF 업로드 → 텍스트 추출 → companies.document_text 저장 (FR-004).

    추출 텍스트는 /company/brain 실행 시 Company Brain LLM 추출 입력으로 재사용된다.
    CPU 바운드 파싱(pypdf)은 이벤트 루프 차단을 피해 스레드풀에서 수행.
    온보딩 'document' 단계면 'brain'으로 전이.
    """
    company = _get_company(db, company_id)
    # Content-Length로 빠른 거부(있으면) + 청크 읽기로 메모리 상한 강제(전량 적재 방지).
    if file.size is not None and file.size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"파일이 너무 큽니다(최대 {MAX_UPLOAD_BYTES // 1024 // 1024}MB).",
        )
    data = await _read_limited(file, MAX_UPLOAD_BYTES)

    try:
        result = await run_in_threadpool(extract_document, file.filename or "", data)
    except DocumentTooLargeError as exc:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(exc)) from exc
    except UnsupportedDocumentError as exc:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, str(exc)) from exc
    except EmptyDocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except DocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc

    company.document_text = result.text
    company.document_filename = file.filename
    if company.onboarding_status == "document":
        company.onboarding_status = "brain"
    db.commit()

    return {
        "status": "parsed",
        "filename": file.filename,
        "size": len(data),
        "page_count": result.page_count,
        "char_count": result.char_count,
        "truncated": result.truncated,
        "preview": result.text[:300],
    }
