"""단위: 회사소개서 텍스트 추출기 (FR-004).

픽스처 tests/fixtures/sample_brochure.pdf(reportlab 생성, 한글 CID 폰트)로 실제 추출 경로
검증. 재생성: python scripts/_gen_pdfs.py.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.services.documents import extractor
from app.services.documents.extractor import (
    MAX_TEXT_CHARS,
    MAX_UPLOAD_BYTES,
    DocumentError,
    DocumentTooLargeError,
    EmptyDocumentError,
    ExtractResult,
    UnsupportedDocumentError,
    extract_document,
)

FIXTURE = Path(__file__).parent.parent / "fixtures" / "sample_brochure.pdf"


def _pdf_bytes() -> bytes:
    return FIXTURE.read_bytes()


def test_extract_pdf_returns_text_and_pagecount() -> None:
    result = extract_document("sample_brochure.pdf", _pdf_bytes())
    assert isinstance(result, ExtractResult)
    assert result.page_count == 1
    assert result.char_count > 50
    assert result.truncated is False
    # 실제 한글 텍스트 레이어 추출 확인
    assert "샘플테크" in result.text
    assert "클라우드" in result.text


def test_extension_check_is_case_insensitive() -> None:
    result = extract_document("BROCHURE.PDF", _pdf_bytes())
    assert result.page_count == 1


def test_unsupported_extension_raises() -> None:
    with pytest.raises(UnsupportedDocumentError):
        extract_document("resume.docx", _pdf_bytes())


def test_no_extension_raises() -> None:
    with pytest.raises(UnsupportedDocumentError):
        extract_document("noext", _pdf_bytes())


def test_too_large_raises_before_parsing() -> None:
    big = b"%PDF-1.4" + b"x" * (MAX_UPLOAD_BYTES + 1)
    with pytest.raises(DocumentTooLargeError):
        extract_document("big.pdf", big)


def test_invalid_pdf_raises_document_error() -> None:
    with pytest.raises(DocumentError):
        extract_document("broken.pdf", b"not a real pdf at all")


def test_blank_extraction_raises_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """텍스트 레이어 없는(스캔) PDF → EmptyDocumentError."""
    monkeypatch.setattr(extractor, "extract_pdf", lambda data: ("   \n\n  ", 4))
    with pytest.raises(EmptyDocumentError):
        extract_document("scan.pdf", b"%PDF-1.4 fake")


def test_long_text_is_truncated(monkeypatch: pytest.MonkeyPatch) -> None:
    long_text = "물" * (MAX_TEXT_CHARS + 500)
    monkeypatch.setattr(extractor, "extract_pdf", lambda data: (long_text, 30))
    result = extract_document("long.pdf", b"%PDF-1.4 fake")
    assert result.truncated is True
    assert result.char_count == MAX_TEXT_CHARS
    assert len(result.text) == MAX_TEXT_CHARS
