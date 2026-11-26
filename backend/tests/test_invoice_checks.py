"""Tests for the invoice helper functions in app/routers/invoices.py:
deterministic validation checks, AI check fallback, PDF text extraction
and AI output validation.
"""
from decimal import Decimal as D

import pytest
from fastapi import HTTPException

from agent.client import AIAgentError
from app.routers import invoices as invoices_module
from app.routers.invoices import (
    extract_text_from_pdf,
    run_ai_invoice_checks,
    run_deterministic_checks,
    validate_ai_output,
)
from tests.conftest import make_pdf


def _invoice(**overrides):
    invoice = {
        "invoice_number": "INV-001",
        "invoice_date": "2026-11-01",
        "due_date": "2026-12-01",
        "subtotal": D("100.00"),
        "tax_amount": D("10.00"),
        "total_amount": D("110.00"),
        "duplicate_of_invoice_id": None,
    }
    invoice.update(overrides)
    return invoice


def _item(line_no=1, quantity="2", unit_price="50.00", line_total="100.00"):
    return {
        "line_no": line_no,
        "quantity": D(quantity),
        "unit_price": D(unit_price),
        "line_total": None if line_total is None else D(line_total),
    }


def _by_type(checks):
    return {c["check_type"]: c for c in checks}


# ---------------------------------------------------------------- run_deterministic_checks

def test_clean_invoice_passes_every_check():
    checks = run_deterministic_checks(_invoice(), [_item()])

    assert [c["check_type"] for c in checks] == [
        "missing_field", "line_total", "invoice_total", "duplicate", "text_readable",
    ]
    assert all(c["result"] == "pass" for c in checks)


def test_missing_fields_are_listed():
    checks = _by_type(run_deterministic_checks(_invoice(due_date=None, tax_amount=None), [_item()]))

    assert checks["missing_field"]["result"] == "fail"
    assert "due_date" in checks["missing_field"]["details"]
    assert "tax_amount" in checks["missing_field"]["details"]


def test_wrong_line_total_fails_with_line_numbers():
    items = [_item(1), _item(2, line_total="99.00"), _item(3, line_total=None)]

    check = _by_type(run_deterministic_checks(_invoice(), items))["line_total"]

    assert check["result"] == "fail"
    assert "[2, 3]" in check["details"]


def test_line_total_allows_one_cent_rounding():
    item = _item(quantity="3", unit_price="33.333", line_total="100.00")  # 99.999
    assert _by_type(run_deterministic_checks(_invoice(), [item]))["line_total"]["result"] == "pass"


def test_no_items_passes_line_total_check():
    assert _by_type(run_deterministic_checks(_invoice(), []))["line_total"]["result"] == "pass"


@pytest.mark.parametrize(
    "overrides",
    [
        {"total_amount": D("120.00")},   # arithmetic mismatch
        {"total_amount": None},          # total missing
    ],
)
def test_invoice_total_mismatch_fails(overrides):
    check = _by_type(run_deterministic_checks(_invoice(**overrides), [_item()]))["invoice_total"]
    assert check["result"] == "fail"


def test_invoice_total_treats_missing_tax_as_zero():
    invoice = _invoice(tax_amount=None, total_amount=D("100.00"))
    assert _by_type(run_deterministic_checks(invoice, [_item()]))["invoice_total"]["result"] == "pass"


def test_duplicate_invoice_fails_and_names_original():
    check = _by_type(run_deterministic_checks(_invoice(duplicate_of_invoice_id=4), [_item()]))["duplicate"]
    assert check["result"] == "fail"
    assert "4" in check["details"]


# ---------------------------------------------------------------- run_ai_invoice_checks

def test_ai_checks_are_returned_when_model_works(monkeypatch):
    expected = [{"check_type": "missing_field", "result": "pass", "details": "[AI advisory] ok"}]
    monkeypatch.setattr(invoices_module, "review_invoice_with_ai", lambda inv, items: expected)
    assert run_ai_invoice_checks(_invoice(), []) == expected


def test_ai_checks_are_skipped_when_model_fails(monkeypatch):
    def boom(inv, items):
        raise AIAgentError("down", "timeout")

    monkeypatch.setattr(invoices_module, "review_invoice_with_ai", boom)
    # Submission must still work on deterministic checks alone.
    assert run_ai_invoice_checks(_invoice(), []) == []


# ---------------------------------------------------------------- extract_text_from_pdf

def test_extract_text_from_pdf_bytes():
    text = extract_text_from_pdf(make_pdf(text="Invoice INV-777"))
    assert "Invoice INV-777" in text


def test_extract_text_from_pdf_path(tmp_path):
    path = tmp_path / "invoice.pdf"
    path.write_bytes(make_pdf(pages=2, text="Page text"))
    assert extract_text_from_pdf(path).count("Page text") == 2


def test_extract_text_from_blank_pdf_is_empty():
    # Scanned PDFs have no text layer; the extract endpoint relies on this being "".
    assert extract_text_from_pdf(make_pdf(text="")) == ""


def test_extract_text_from_corrupt_pdf_returns_400():
    with pytest.raises(HTTPException) as exc:
        extract_text_from_pdf(b"not a pdf")
    assert exc.value.status_code == 400


# ---------------------------------------------------------------- validate_ai_output

def test_validate_ai_output_accepts_sanitised_agent_result():
    result = validate_ai_output({
        "invoice_number": "INV-1",
        "invoice_date": "2026-11-15",
        "currency": "USD",
        "total_amount": 110.0,
        "items": [{"line_no": 1, "item_name": "Pen", "quantity": 1.0, "unit_price": 2.0, "line_total": 2.0}],
    })
    assert result.total_amount == D("110.0")
    assert result.items[0].item_name == "Pen"


def test_validate_ai_output_raises_value_error_on_bad_data():
    with pytest.raises(ValueError, match="AI output validation failed"):
        validate_ai_output({"total_amount": -5})
