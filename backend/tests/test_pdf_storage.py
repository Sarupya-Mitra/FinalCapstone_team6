"""Tests for app/services/pdf_storage.py (PDF compression and DB storage)."""
import hashlib

import pymupdf
import pytest
from fastapi import HTTPException

from app.services.pdf_storage import CompressedPdf, compress_pdf, load_pdf, upload_pdf
from tests.conftest import FakeConnection, make_pdf


def test_compress_pdf_returns_metadata_for_valid_pdf(pdf_bytes):
    result = compress_pdf(pdf_bytes)

    assert result.page_count == 1
    assert result.original_size == len(pdf_bytes)
    assert result.sha256 == hashlib.sha256(pdf_bytes).hexdigest()
    assert result.stored_size == len(result.data)


def test_compress_pdf_never_grows_the_file(pdf_bytes):
    result = compress_pdf(pdf_bytes)
    assert result.stored_size <= len(pdf_bytes)


def test_compressed_pdf_is_still_a_readable_pdf():
    raw = make_pdf(pages=3, text="Hello invoice")
    result = compress_pdf(raw)

    with pymupdf.open(stream=result.data, filetype="pdf") as doc:
        assert doc.page_count == 3
        assert "Hello invoice" in doc[0].get_text()


def test_compress_pdf_rejects_non_pdf_bytes():
    with pytest.raises(HTTPException) as exc:
        compress_pdf(b"this is definitely not a pdf")
    assert exc.value.status_code == 400


def test_compress_pdf_rejects_password_protected_pdf():
    doc = pymupdf.open()
    doc.new_page()
    raw = doc.tobytes(encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="secret", owner_pw="owner")
    doc.close()

    with pytest.raises(HTTPException) as exc:
        compress_pdf(raw)
    assert exc.value.status_code == 400
    assert "Password" in exc.value.detail


def test_compress_pdf_returns_413_when_over_limit(pdf_bytes):
    with pytest.raises(HTTPException) as exc:
        compress_pdf(pdf_bytes, max_bytes=10)
    assert exc.value.status_code == 413


def test_upload_pdf_inserts_row_and_returns_metadata():
    pdf = CompressedPdf(data=b"%PDF-small", original_size=500, page_count=2, sha256="ab" * 32)
    conn = FakeConnection(
        results=[(11, 5, 500, 10, 2, "2026-11-26")],
        descriptions=[["file_id", "invoice_id", "original_size_bytes",
                       "stored_size_bytes", "page_count", "uploaded_at"]],
    )

    with conn.cursor() as cursor:
        meta = upload_pdf(cursor, 5, "invoice.pdf", pdf)

    assert meta["file_id"] == 11
    assert meta["stored_size_bytes"] == 10
    sql, params = conn.executed[0]
    assert sql.startswith("INSERT INTO invoice_files")
    assert params == (5, b"%PDF-small", "invoice.pdf", 500, 10, 2, "ab" * 32)


def test_load_pdf_returns_bytes_when_stored():
    conn = FakeConnection(results=[(memoryview(b"%PDF-data"),)])
    with conn.cursor() as cursor:
        assert load_pdf(cursor, 5) == b"%PDF-data"
    assert conn.executed[0][1] == (5,)


def test_load_pdf_returns_none_when_missing():
    conn = FakeConnection(results=[None])
    with conn.cursor() as cursor:
        assert load_pdf(cursor, 5) is None
