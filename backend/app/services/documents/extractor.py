"""회사소개서 → 텍스트 추출 (FR-004). 정본: company-brain.md §4.

업로드된 PDF에서 텍스트 레이어를 추출해 Company Brain(build_company_context)의
`document_text` 인자로 공급한다. 추출 텍스트는 companies.document_text에 보관되어
이후 /company/brain 재실행 시 재사용된다.

설계 결정:
  - 라이브러리: pypdf(순수 파이썬, 시스템 의존성 없음 — Windows 친화).
  - 스캔/이미지 PDF는 텍스트 레이어가 없어 추출량이 적거나 0 → EmptyDocumentError.
    OCR(무거운 의존성)은 범위 밖(TODO 후속).
  - DOCX/PPTX는 SUPPORTED_EXTENSIONS 확장으로 후속 대응(현재 PDF만).
"""
from __future__ import annotations

import io
import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 업로드 상한 — 과대 파일/메모리 보호. 회사소개서는 통상 수 MB.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20MB
# 저장/LLM 입력 캡 — 원문이 길어도 이 길이까지만 보관(임베딩/LLM 비용·DB 보호).
MAX_TEXT_CHARS = 20_000
# 페이지 상한 — 압축폭탄(소형 파일이 수십만 페이지로 팽창) 방어. 회사소개서엔 충분.
MAX_PDF_PAGES = 500

SUPPORTED_EXTENSIONS = (".pdf",)


class DocumentError(Exception):
    """문서 처리 기반 예외."""


class UnsupportedDocumentError(DocumentError):
    """지원하지 않는 확장자."""


class DocumentTooLargeError(DocumentError):
    """업로드 상한 초과."""


class EmptyDocumentError(DocumentError):
    """추출 텍스트가 비어 있음(스캔본/빈 파일 — OCR 필요)."""


@dataclass(frozen=True)
class ExtractResult:
    """추출 결과. text는 정규화·길이 캡 적용된 최종 텍스트."""

    text: str
    page_count: int
    char_count: int
    truncated: bool


def _ext(filename: str) -> str:
    """파일명에서 소문자 확장자(.포함) 추출."""
    idx = filename.rfind(".")
    return filename[idx:].lower() if idx != -1 else ""


def _normalize(text: str) -> str:
    """추출 텍스트 정돈: 줄별 trim, 과다 공백/빈 줄 축소.

    pypdf 추출물은 페이지 경계·레이아웃으로 공백/개행이 과다해 임베딩 노이즈가 됨.
    """
    # 각 줄 우측 공백 제거 + 내부 다중 공백 1칸으로
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    # 연속 빈 줄 1개로 축소
    out: list[str] = []
    blank = False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def extract_pdf(data: bytes) -> tuple[str, int]:
    """PDF 바이트 → (원시 추출 텍스트, 페이지 수).

    pypdf로 페이지별 text layer 추출. 암호화 PDF는 빈 암호 복호화 시도 후 실패 시 에러.
    """
    from pypdf import PdfReader  # noqa: PLC0415
    from pypdf.errors import PdfReadError  # noqa: PLC0415

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            # 빈 사용자 암호로 복호화 시도(흔한 케이스). 실패하면 처리 불가.
            try:
                reader.decrypt("")
            except Exception as exc:  # noqa: BLE001
                raise DocumentError("암호로 보호된 PDF는 처리할 수 없습니다.") from exc
        page_count = len(reader.pages)
        if page_count > MAX_PDF_PAGES:
            raise DocumentTooLargeError(
                f"페이지가 너무 많습니다({page_count}p). 최대 {MAX_PDF_PAGES}p까지 처리합니다."
            )
        # 텍스트 캡 도달 시 남은 페이지 추출 생략 — 전 페이지를 메모리에 펼치지 않음(폭탄 방어).
        parts: list[str] = []
        acc = 0
        for page in reader.pages:
            chunk = page.extract_text() or ""
            parts.append(chunk)
            acc += len(chunk)
            if acc >= MAX_TEXT_CHARS:
                break
    except DocumentError:
        raise
    except (PdfReadError, OSError, ValueError, KeyError) as exc:
        raise DocumentError(f"PDF를 읽을 수 없습니다: {exc}") from exc

    return "\n".join(parts), page_count


def extract_document(filename: str, data: bytes) -> ExtractResult:
    """업로드 파일(파일명+바이트) → ExtractResult.

    Raises:
        DocumentTooLargeError: MAX_UPLOAD_BYTES 초과.
        UnsupportedDocumentError: 지원하지 않는 확장자.
        EmptyDocumentError: 추출 텍스트가 비어 있음(스캔본 추정).
        DocumentError: 그 외 파싱 실패(손상/암호화).
    """
    if len(data) > MAX_UPLOAD_BYTES:
        raise DocumentTooLargeError(
            f"파일이 너무 큽니다({len(data) // 1024 // 1024}MB). "
            f"최대 {MAX_UPLOAD_BYTES // 1024 // 1024}MB까지 허용됩니다."
        )

    ext = _ext(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise UnsupportedDocumentError(
            f"지원하지 않는 형식입니다({ext or '확장자 없음'}). "
            f"지원: {', '.join(SUPPORTED_EXTENSIONS)}"
        )

    raw_text, page_count = extract_pdf(data)
    text = _normalize(raw_text)

    truncated = len(text) > MAX_TEXT_CHARS
    if truncated:
        text = text[:MAX_TEXT_CHARS]

    if not text.strip():
        raise EmptyDocumentError(
            "텍스트를 추출하지 못했습니다. 스캔(이미지) PDF는 현재 지원하지 않습니다."
        )

    logger.info(
        "문서 추출 완료: pages=%d chars=%d truncated=%s", page_count, len(text), truncated
    )
    return ExtractResult(
        text=text, page_count=page_count, char_count=len(text), truncated=truncated
    )
