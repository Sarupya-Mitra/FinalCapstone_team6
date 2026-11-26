"""Tests for app/routers/vendors.py with a fake database."""
from datetime import datetime

import psycopg2.errors
import pytest
from fastapi import HTTPException

from app.routers.vendors import create_vendor, get_all_vendors, get_vendor, update_vendor
from app.schemas.vendor import VendorCreate, VendorResponse, VendorUpdate

MODULE = "app.routers.vendors"
CLERK = {"id": 3, "role": "clerk"}
NOW = datetime(2026, 11, 26, 10, 0)


def _row(vendor_id=1, name="Acme Office Supplies", active=True):
    return (vendor_id, name, "ap@acme.example", "ACME-TX-1001", active, NOW, NOW)


# ---------------------------------------------------------------- list / get

def test_get_all_vendors_maps_rows_to_dicts(fake_db):
    conn = fake_db(MODULE, results=[[_row(1), _row(2, "Nimbus")]])

    vendors = get_all_vendors(current_user=CLERK)

    assert [v["vendor_name"] for v in vendors] == ["Acme Office Supplies", "Nimbus"]
    assert all(VendorResponse(**v) for v in vendors)
    assert conn.closed


def test_get_all_vendors_empty(fake_db):
    fake_db(MODULE, results=[[]])
    assert get_all_vendors(current_user=CLERK) == []


def test_get_vendor_returns_vendor(fake_db):
    conn = fake_db(MODULE, results=[_row(1)])

    vendor = get_vendor(id=1, current_user=CLERK)

    assert vendor["vendor_id"] == 1
    assert VendorResponse(**vendor).tax_id == "ACME-TX-1001"
    # Regression: the id must be passed as a tuple, not a bare int.
    assert conn.executed[0][1] == (1,)
    assert conn.closed


def test_get_vendor_missing_returns_404(fake_db):
    conn = fake_db(MODULE, results=[None])

    with pytest.raises(HTTPException) as exc:
        get_vendor(id=999, current_user=CLERK)

    assert exc.value.status_code == 404
    assert conn.closed


# ---------------------------------------------------------------- create

def test_create_vendor_inserts_and_commits(fake_db):
    conn = fake_db(MODULE, results=[_row(5, "New Co")])
    payload = VendorCreate(vendor_name="New Co", contact_reference="ap@new.example", tax_id="NEW-1")

    vendor = create_vendor(vendor=payload, current_user=CLERK)

    assert vendor["vendor_id"] == 5
    assert conn.committed
    sql, params = conn.executed[0]
    assert sql.startswith("INSERT INTO vendors")
    assert params == ("New Co", "ap@new.example", "NEW-1", True)


def test_create_duplicate_vendor_returns_409_and_rolls_back(fake_db):
    conn = fake_db(MODULE, errors=[psycopg2.errors.UniqueViolation("duplicate key")])
    payload = VendorCreate(vendor_name="Acme", contact_reference="ap@acme.example", tax_id="T")

    with pytest.raises(HTTPException) as exc:
        create_vendor(vendor=payload, current_user=CLERK)

    assert exc.value.status_code == 409
    assert conn.rolled_back
    assert not conn.committed
    assert conn.closed


# ---------------------------------------------------------------- update

def test_update_vendor_only_sets_provided_fields(fake_db):
    conn = fake_db(MODULE, results=[_row(1, active=False)])

    vendor = update_vendor(id=1, vendor=VendorUpdate(active=False), current_user=CLERK)

    assert vendor["active"] is False
    assert conn.committed
    sql, params = conn.executed[0]
    assert "active = %s" in sql
    assert "vendor_name = %s" not in sql
    assert "updated_at = CURRENT_TIMESTAMP" in sql
    assert params == [False, 1]


def test_update_vendor_with_no_fields_returns_current_without_writing(fake_db):
    conn = fake_db(MODULE, results=[_row(1)])

    vendor = update_vendor(id=1, vendor=VendorUpdate(), current_user=CLERK)

    assert vendor["vendor_name"] == "Acme Office Supplies"
    assert conn.executed[0][0].startswith("SELECT")
    assert not conn.committed


@pytest.mark.parametrize("update", [VendorUpdate(), VendorUpdate(tax_id="X")])
def test_update_missing_vendor_returns_404(fake_db, update):
    fake_db(MODULE, results=[None])
    with pytest.raises(HTTPException) as exc:
        update_vendor(id=999, vendor=update, current_user=CLERK)
    assert exc.value.status_code == 404


def test_update_vendor_duplicate_contact_returns_409(fake_db):
    conn = fake_db(MODULE, errors=[psycopg2.errors.UniqueViolation("duplicate key")])

    with pytest.raises(HTTPException) as exc:
        update_vendor(id=1, vendor=VendorUpdate(contact_reference="taken@x.example"), current_user=CLERK)

    assert exc.value.status_code == 409
    assert conn.rolled_back
