"""Tests for GET /invoices (get_invoices) in app/routers/invoices.py."""
from datetime import datetime

import pytest

from app.routers.invoices import get_invoices
from app.schemas.invoice import InvoiceResponse

MODULE = "app.routers.invoices"
CLERK = {"id": 3, "name": "Anita Sharma", "email": "anita.clerk@example.com", "role": "clerk"}

COLUMNS = [
    "invoice_id", "vendor_id", "invoice_number", "invoice_date", "due_date", "currency",
    "subtotal", "tax_amount", "total_amount", "original_filename", "file_size_bytes",
    "status", "is_verified", "duplicate_of_invoice_id", "uploaded_by_clerk_id",
    "created_at", "updated_at",
]


def _row(invoice_id, status="uploaded"):
    now = datetime(2026, 11, 26)
    return (invoice_id, 1, None, None, None, "USD", None, None, None,
            "a.pdf", 1000, status, False, None, 3, now, now)


def _call(**kwargs):
    args = {"vendor_id": None, "status": None, "limit": 50, "offset": 0, "current_user": CLERK}
    args.update(kwargs)
    return get_invoices(**args)


def test_returns_invoices_matching_response_schema(fake_db):
    conn = fake_db(MODULE, results=[[_row(1), _row(2, "extracted")]], descriptions=[COLUMNS])

    invoices = _call()

    assert [i["invoice_id"] for i in invoices] == [1, 2]
    assert all(InvoiceResponse(**i) for i in invoices)
    assert conn.closed


def test_only_returns_invoices_of_logged_in_clerk(fake_db):
    conn = fake_db(MODULE, results=[[]], descriptions=[COLUMNS])

    _call()

    sql, params = conn.executed[0]
    assert "AND uploaded_by_clerk_id = %s" in sql
    assert params[0] == CLERK["id"]


def test_selects_columns_that_exist_in_the_model():
    # Regression: the live DB once had uploaded_by instead of uploaded_by_clerk_id.
    import models

    model_columns = {c.name for c in models.Invoice.__table__.columns}
    assert set(COLUMNS) <= model_columns


def test_applies_vendor_and_status_filters(fake_db):
    conn = fake_db(MODULE, results=[[]], descriptions=[COLUMNS])

    _call(vendor_id=2, status="pending_approval", limit=20, offset=40)

    sql, params = conn.executed[0]
    assert "AND vendor_id = %s" in sql
    assert "AND status = %s" in sql
    assert sql.endswith("ORDER BY created_at DESC LIMIT %s OFFSET %s")
    assert params == (3, 2, "pending_approval", 20, 40)


@pytest.mark.parametrize("kwargs, absent", [({"status": "approved"}, "vendor_id = %s"),
                                            ({"vendor_id": 1}, "status = %s")])
def test_omits_filters_that_are_not_given(fake_db, kwargs, absent):
    conn = fake_db(MODULE, results=[[]], descriptions=[COLUMNS])
    _call(**kwargs)
    assert absent not in conn.executed[0][0]


def test_connection_closed_even_when_query_fails(fake_db):
    conn = fake_db(MODULE, errors=[RuntimeError("db down")])
    with pytest.raises(RuntimeError):
        _call()
    assert conn.closed
