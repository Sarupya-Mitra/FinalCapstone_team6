"""Tests for duplicate-PDF detection on upload and manual entry after failed extraction."""
import io
from decimal import Decimal

import pytest
from fastapi import HTTPException, UploadFile

from app.routers import invoices
from app.schemas.invoice import InvoiceCorrectionSubmit

CLERK = {"id": 7, "role": "clerk"}
DUPLICATE_COLUMNS = ["invoice_id", "invoice_number", "status", "original_filename", "uploaded_by_clerk_id"]


def _upload(pdf_bytes):
    return UploadFile(file=io.BytesIO(pdf_bytes), filename="invoice.pdf")


@pytest.mark.parametrize("owner, yours", [(7, True), (99, False)])
def test_upload_rejects_pdf_that_was_already_uploaded(fake_db, monkeypatch, tmp_path, pdf_bytes, owner, yours):
    monkeypatch.setattr(invoices, "UPLOAD_DIR", tmp_path)
    conn = fake_db(
        "app.routers.invoices",
        results=[(12, "INV-1", "approved", "first.pdf", owner)],
        descriptions=[[], DUPLICATE_COLUMNS],
    )

    with pytest.raises(HTTPException) as exc:
        invoices.upload_invoice(vendor_id=1, file=_upload(pdf_bytes), current_user=CLERK)

    assert exc.value.status_code == 409
    assert exc.value.detail["duplicate_invoice_id"] == 12
    assert exc.value.detail["uploaded_by_you"] is yours
    assert "invoice #12" in exc.value.detail["message"]
    # Nothing was written: no INSERT ran and no file was saved to disk.
    assert not any(sql.startswith("INSERT") for sql, _ in conn.executed)
    assert list(tmp_path.iterdir()) == []
    assert conn.rolled_back and conn.closed


def test_upload_checks_hash_under_a_lock(fake_db, monkeypatch, tmp_path, pdf_bytes):
    monkeypatch.setattr(invoices, "UPLOAD_DIR", tmp_path)
    conn = fake_db("app.routers.invoices", results=[(12, "INV-1", "uploaded", "a.pdf", 7)],
                   descriptions=[[], DUPLICATE_COLUMNS])

    with pytest.raises(HTTPException):
        invoices.upload_invoice(vendor_id=1, file=_upload(pdf_bytes), current_user=CLERK)

    lock_sql, lock_params = conn.executed[0]
    check_sql, check_params = conn.executed[1]
    assert "pg_advisory_xact_lock" in lock_sql
    assert "invoice_original_files" in check_sql and "invoice_files" in check_sql
    assert lock_params[0] == check_params[0] == check_params[1]  # same SHA-256 everywhere
    assert len(lock_params[0]) == 64


def _correction():
    return InvoiceCorrectionSubmit(
        invoice_number="INV-9", invoice_date=None, due_date=None, currency="USD",
        subtotal=Decimal("10"), tax_amount=Decimal("0"), total_amount=Decimal("10"), items=[],
    )


INVOICE_COLUMNS = ["invoice_id", "invoice_number", "invoice_date", "due_date", "currency",
                   "subtotal", "tax_amount", "total_amount", "status"]


def test_manual_entry_allowed_on_uploaded_invoice_and_marks_it_extracted(fake_db):
    conn = fake_db(
        "app.routers.invoices",
        results=[(5, None, None, None, "USD", None, None, None, "uploaded"), []],
        descriptions=[INVOICE_COLUMNS],
    )

    result = invoices.correct_invoice(5, _correction(), current_user=CLERK)

    assert result["status"] == "extracted"
    update = next(sql for sql, _ in conn.executed if sql.startswith("UPDATE invoices"))
    assert "status = 'extracted'" in update
    assert conn.committed


@pytest.mark.parametrize("status", ["pending_approval", "approved", "rejected", "discrepancy"])
def test_manual_entry_refused_after_submission(fake_db, status):
    fake_db(
        "app.routers.invoices",
        results=[(5, "INV-9", None, None, "USD", 10, 0, 10, status)],
        descriptions=[INVOICE_COLUMNS],
    )

    with pytest.raises(HTTPException) as exc:
        invoices.correct_invoice(5, _correction(), current_user=CLERK)
    assert exc.value.status_code == 400
