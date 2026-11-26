"""Tests for the Pydantic request/response schemas in app/schemas/."""
from datetime import date, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.approval import ApprovalDecisionSubmit
from app.schemas.invoice import (
    InvoiceCorrectionSubmit,
    InvoiceExtractionResult,
    InvoiceItemSubmit,
    InvoiceResponse,
    InvoiceSubmit,
)
from app.schemas.vendor import VendorCreate, VendorUpdate


# ---------------------------------------------------------------- invoices

def test_invoice_submit_accepts_valid_payload():
    invoice = InvoiceSubmit(
        invoice_number="INV-001",
        invoice_date="2026-11-01",
        currency="USD",
        subtotal="100.00",
        tax_amount="10.00",
        total_amount="110.00",
        items=[{"line_no": 1, "item_name": "Paper", "quantity": 2, "unit_price": "50"}],
    )
    assert invoice.invoice_date == date(2026, 11, 1)
    assert invoice.total_amount == Decimal("110.00")
    assert invoice.items[0].line_total is None


@pytest.mark.parametrize("currency", ["US", "USDT", ""])
def test_invoice_submit_requires_three_letter_currency(currency):
    with pytest.raises(ValidationError):
        InvoiceSubmit(currency=currency)


@pytest.mark.parametrize("field", ["subtotal", "tax_amount", "total_amount"])
def test_invoice_submit_rejects_negative_amounts(field):
    with pytest.raises(ValidationError):
        InvoiceSubmit(currency="USD", **{field: "-1"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"line_no": 0},          # line numbers start at 1
        {"item_name": ""},       # name required
        {"quantity": 0},         # quantity must be > 0
        {"unit_price": -5},      # price can't be negative
        {"line_total": -1},
    ],
)
def test_invoice_item_rejects_invalid_values(overrides):
    data = {"line_no": 1, "item_name": "Paper", "quantity": 1, "unit_price": 1, **overrides}
    with pytest.raises(ValidationError):
        InvoiceItemSubmit(**data)


def test_invoice_item_allows_zero_unit_price():
    assert InvoiceItemSubmit(line_no=1, item_name="Free sample", quantity=1, unit_price=0).unit_price == 0


def test_extraction_result_defaults_to_usd_and_empty_items():
    result = InvoiceExtractionResult()
    assert result.currency == "USD"
    assert result.items == []
    assert result.invoice_number is None


def test_correction_submit_requires_items_list():
    with pytest.raises(ValidationError):
        InvoiceCorrectionSubmit(currency="USD")
    assert InvoiceCorrectionSubmit(currency="USD", items=[]).items == []


def _invoice_row(**overrides):
    row = {
        "invoice_id": 1,
        "vendor_id": 1,
        "invoice_number": None,
        "invoice_date": None,
        "due_date": None,
        "currency": "USD",
        "subtotal": None,
        "tax_amount": None,
        "total_amount": None,
        "original_filename": "a.pdf",
        "file_size_bytes": 100,
        "status": "uploaded",
        "is_verified": False,
        "duplicate_of_invoice_id": None,
        "uploaded_by_clerk_id": 3,
        "created_at": datetime(2026, 11, 1),
        "updated_at": datetime(2026, 11, 1),
    }
    row.update(overrides)
    return row


@pytest.mark.parametrize(
    "status", ["uploaded", "extracted", "pending_approval", "discrepancy", "approved", "rejected"]
)
def test_invoice_response_accepts_every_known_status(status):
    assert InvoiceResponse(**_invoice_row(status=status)).status == status


def test_invoice_response_rejects_unknown_status():
    with pytest.raises(ValidationError):
        InvoiceResponse(**_invoice_row(status="paid"))


def test_invoice_response_requires_clerk_id():
    # Regression: the DB column was once called uploaded_by, which broke the clerk page.
    row = _invoice_row()
    row.pop("uploaded_by_clerk_id")
    with pytest.raises(ValidationError):
        InvoiceResponse(**row)


# ---------------------------------------------------------------- vendors

def test_vendor_create_defaults_to_active():
    vendor = VendorCreate(vendor_name="Acme", contact_reference="ap@acme.example", tax_id="T-1")
    assert vendor.active is True


@pytest.mark.parametrize("field", ["vendor_name", "contact_reference", "tax_id"])
def test_vendor_create_rejects_empty_strings(field):
    data = {"vendor_name": "Acme", "contact_reference": "ap@acme.example", "tax_id": "T-1", field: ""}
    with pytest.raises(ValidationError):
        VendorCreate(**data)


def test_vendor_create_rejects_overlong_name():
    with pytest.raises(ValidationError):
        VendorCreate(vendor_name="x" * 101, contact_reference="c", tax_id="t")


def test_vendor_update_allows_partial_update():
    update = VendorUpdate(active=False)
    assert update.model_dump(exclude_unset=True) == {"active": False}


def test_vendor_update_rejects_explicit_nulls():
    with pytest.raises(ValidationError, match="cannot be null"):
        VendorUpdate(vendor_name=None)


# ---------------------------------------------------------------- approvals

@pytest.mark.parametrize("decision", ["approved", "rejected"])
def test_approval_decision_accepts_valid_decisions(decision):
    assert ApprovalDecisionSubmit(decision=decision, note="Looks fine").decision == decision


def test_approval_decision_rejects_unknown_decision():
    with pytest.raises(ValidationError):
        ApprovalDecisionSubmit(decision="pending", note="x")


def test_approval_decision_requires_a_note():
    with pytest.raises(ValidationError):
        ApprovalDecisionSubmit(decision="rejected", note="")
