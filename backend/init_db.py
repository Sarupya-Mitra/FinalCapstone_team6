"""Create the invoice_processing database, its tables, and fictional seed data.

Usage (from the backend/ folder):
    python init_db.py            # create DB + tables, seed if empty
    python init_db.py --reset    # DROP all tables, recreate, reseed
    python init_db.py --no-seed  # create DB + tables only
"""
import argparse
from datetime import date
from decimal import Decimal as D

from sqlalchemy import func, select

import models  # noqa: F401  (registers tables on Base.metadata)
from database import DB_NAME, Base, SessionLocal, check_connection, create_database_if_missing, engine
from models import (
    ExtractionRun,
    Invoice,
    InvoiceApproval,
    InvoiceCheck,
    InvoiceCorrection,
    InvoiceItem,
    Vendor,
)

SEED_PROVIDER = "seed"
SEED_MODEL = "seed-fixture"


def _items(rows):
    """rows: (name, qty, unit_price, stated_line_total)"""
    return [
        InvoiceItem(line_no=i, item_name=n, quantity=D(q), unit_price=D(p), line_total=D(t), source="ai")
        for i, (n, q, p, t) in enumerate(rows, start=1)
    ]


def _extraction(number, inv_date, rows, total, uncertain=()):
    return {
        "invoice_number": number or "not_found",
        "invoice_date": inv_date.isoformat() if inv_date else None,
        "line_items": [
            {"item_name": n, "quantity": float(q), "unit_price": float(p), "line_total": float(t)}
            for n, q, p, t in rows
        ],
        "extracted_total": float(total) if total is not None else None,
        "uncertain_fields": list(uncertain),
    }


def seed(session) -> None:
    # ---------------- Vendors ----------------
    acme = Vendor(vendor_name="Acme Office Supplies", contact_reference="ap@acme-office.example", tax_id="ACME-TX-1001")
    nimbus = Vendor(vendor_name="Nimbus Cloud Services", contact_reference="billing@nimbus-cloud.example", tax_id="NCS-TX-2002")
    blueriver = Vendor(vendor_name="BlueRiver Logistics", contact_reference="accounts@blueriver.example", tax_id="BRL-TX-3003")
    session.add_all([acme, nimbus, blueriver])
    session.flush()

    # 1) Valid invoice, approved ------------------------------------------
    rows1 = [("A4 Copy Paper (box)", "10", "4.50", "45.00"), ("Black Toner Cartridge", "2", "60.00", "120.00")]
    inv1 = Invoice(
        vendor=acme, invoice_number="INV-1001", invoice_date=date(2026, 10, 2), due_date=date(2026, 11, 1),
        subtotal=D("165.00"), tax_amount=D("16.50"), total_amount=D("181.50"),
        file_path="uploads/invoice_0001.pdf", original_filename="acme_INV-1001.pdf", file_size_bytes=48213,
        status="approved", is_verified=True, uploaded_by="clerk.anita",
        items=_items(rows1),
        extraction_runs=[ExtractionRun(
            extracted_json=_extraction("INV-1001", date(2026, 10, 2), rows1, "181.50"),
            provider=SEED_PROVIDER, model_name=SEED_MODEL, status="success", duration_ms=1840,
            ai_summary="All line totals and the invoice total reconcile. No issues found.")],
        checks=[
            InvoiceCheck(check_type="duplicate", result="pass", details="No other invoice INV-1001 for this vendor."),
            InvoiceCheck(check_type="line_total", result="pass", details="All 2 line totals match quantity x unit price."),
            InvoiceCheck(check_type="invoice_total", result="pass", details="165.00 + 16.50 tax = 181.50 matches stated total."),
            InvoiceCheck(check_type="missing_field", result="pass", details="All required fields present."),
        ],
        approvals=[InvoiceApproval(reviewer="approver.rahul", decision="approved",
                                   note="Matches PO-7781; goods received in full.")],
    )

    # 2) Arithmetic mismatch ----------------------------------------------
    rows2 = [("Ballpoint Pens (pack of 10)", "50", "1.20", "65.00"), ("Heavy-duty Stapler", "5", "8.00", "40.00")]
    inv2 = Invoice(
        vendor=acme, invoice_number="INV-1002", invoice_date=date(2026, 10, 15), due_date=date(2026, 11, 14),
        subtotal=D("105.00"), tax_amount=D("10.50"), total_amount=D("115.50"),
        file_path="uploads/invoice_0002.pdf", original_filename="acme_INV-1002.pdf", file_size_bytes=47102,
        status="discrepancy", is_verified=True, uploaded_by="clerk.anita",
        items=_items(rows2),
        extraction_runs=[ExtractionRun(
            extracted_json=_extraction("INV-1002", date(2026, 10, 15), rows2, "115.50", ["line_items[0].line_total"]),
            provider=SEED_PROVIDER, model_name=SEED_MODEL, status="success", duration_ms=2010,
            ai_summary="Line 1 states 65.00 but 50 x 1.20 = 60.00, so the subtotal is overstated by 5.00.")],
        checks=[
            InvoiceCheck(check_type="duplicate", result="pass", details="First invoice INV-1002 for this vendor."),
            InvoiceCheck(check_type="line_total", result="fail",
                         details="Line 1: stated 65.00, computed 50 x 1.20 = 60.00 (diff 5.00)."),
            InvoiceCheck(check_type="invoice_total", result="fail",
                         details="Computed subtotal 100.00 vs stated 105.00; expected total 110.50 vs stated 115.50."),
            InvoiceCheck(check_type="missing_field", result="pass", details="All required fields present."),
        ],
    )
    session.add_all([inv1, inv2])
    session.flush()

    # 3) Duplicate invoice number, same vendor (kept, flagged, original untouched)
    inv3 = Invoice(
        vendor=acme, invoice_number="INV-1002", invoice_date=date(2026, 10, 15), due_date=date(2026, 11, 14),
        subtotal=D("105.00"), tax_amount=D("10.50"), total_amount=D("115.50"),
        file_path="uploads/invoice_0003.pdf", original_filename="acme_INV-1002_resend.pdf", file_size_bytes=47102,
        status="discrepancy", is_verified=False, uploaded_by="clerk.anita",
        duplicate_of_invoice_id=inv2.invoice_id,
        items=_items(rows2),
        extraction_runs=[ExtractionRun(
            extracted_json=_extraction("INV-1002", date(2026, 10, 15), rows2, "115.50"),
            provider=SEED_PROVIDER, model_name=SEED_MODEL, status="success", duration_ms=1932)],
        checks=[InvoiceCheck(check_type="duplicate", result="fail",
                             details=f"Invoice INV-1002 already exists for Acme Office Supplies (invoice_id={inv2.invoice_id}).")],
    )

    # 4) Missing tax / total ----------------------------------------------
    rows4 = [("Cloud Hosting - October", "1", "450.00", "450.00"), ("Support Hours", "6", "75.00", "450.00")]
    inv4 = Invoice(
        vendor=nimbus, invoice_number="NCS-2026-077", invoice_date=date(2026, 10, 5), due_date=date(2026, 11, 4),
        subtotal=D("900.00"), tax_amount=None, total_amount=None,
        file_path="uploads/invoice_0004.pdf", original_filename="nimbus_NCS-2026-077.pdf", file_size_bytes=51877,
        status="discrepancy", is_verified=False, uploaded_by="clerk.anita",
        items=_items(rows4),
        extraction_runs=[ExtractionRun(
            extracted_json=_extraction("NCS-2026-077", date(2026, 10, 5), rows4, None, ["tax_amount", "extracted_total"]),
            provider=SEED_PROVIDER, model_name=SEED_MODEL, status="partial", duration_ms=2244,
            ai_summary="Document shows a subtotal of 900.00 but no tax line or grand total.")],
        checks=[
            InvoiceCheck(check_type="duplicate", result="pass", details="No other invoice NCS-2026-077 for this vendor."),
            InvoiceCheck(check_type="line_total", result="pass", details="All 2 line totals match quantity x unit price."),
            InvoiceCheck(check_type="missing_field", result="fail", details="Missing required fields: tax_amount, total_amount."),
        ],
    )

    # 5) Valid, waiting for approver --------------------------------------
    rows5 = [("Cloud Hosting - November", "1", "450.00", "450.00"), ("Backup Storage 500GB", "2", "25.00", "50.00")]
    inv5 = Invoice(
        vendor=nimbus, invoice_number="NCS-2026-078", invoice_date=date(2026, 11, 3), due_date=date(2026, 12, 3),
        subtotal=D("500.00"), tax_amount=D("50.00"), total_amount=D("550.00"),
        file_path="uploads/invoice_0005.pdf", original_filename="nimbus_NCS-2026-078.pdf", file_size_bytes=50311,
        status="pending_approval", is_verified=True, uploaded_by="clerk.anita",
        items=_items(rows5),
        extraction_runs=[ExtractionRun(
            extracted_json=_extraction("NCS-2026-078", date(2026, 11, 3), rows5, "550.00"),
            provider=SEED_PROVIDER, model_name=SEED_MODEL, status="success", duration_ms=1766,
            ai_summary="All checks passed.")],
        checks=[
            InvoiceCheck(check_type="duplicate", result="pass", details="No other invoice NCS-2026-078 for this vendor."),
            InvoiceCheck(check_type="line_total", result="pass", details="All 2 line totals match quantity x unit price."),
            InvoiceCheck(check_type="invoice_total", result="pass", details="500.00 + 50.00 tax = 550.00 matches stated total."),
            InvoiceCheck(check_type="missing_field", result="pass", details="All required fields present."),
        ],
    )

    # 6) Clerk corrected a wrong AI field, then approver rejected ---------
    rows6 = [("Freight Mumbai -> Pune (pallet)", "3", "220.00", "660.00"), ("Handling Fee", "1", "40.00", "40.00")]
    inv6 = Invoice(
        vendor=blueriver, invoice_number="BRL-5531", invoice_date=date(2026, 10, 28), due_date=date(2026, 11, 27),
        subtotal=D("700.00"), tax_amount=D("70.00"), total_amount=D("770.00"),
        file_path="uploads/invoice_0006.pdf", original_filename="blueriver_BRL-5531.pdf", file_size_bytes=45520,
        status="rejected", is_verified=True, uploaded_by="clerk.anita",
        items=_items(rows6),
        # AI originally read the date as 2026-08-28; kept here for traceability.
        extraction_runs=[ExtractionRun(
            extracted_json=_extraction("BRL-5531", date(2026, 8, 28), rows6, "770.00", ["invoice_date"]),
            provider=SEED_PROVIDER, model_name=SEED_MODEL, status="success", duration_ms=2105,
            ai_summary="Invoice date is ambiguous in the document header; please verify.")],
        corrections=[InvoiceCorrection(field_name="invoice_date", old_value="2026-08-28", new_value="2026-10-28",
                                       corrected_by="clerk.anita")],
        checks=[
            InvoiceCheck(check_type="duplicate", result="pass", details="No other invoice BRL-5531 for this vendor."),
            InvoiceCheck(check_type="line_total", result="pass", details="All 2 line totals match quantity x unit price."),
            InvoiceCheck(check_type="invoice_total", result="pass", details="700.00 + 70.00 tax = 770.00 matches stated total."),
            InvoiceCheck(check_type="missing_field", result="pass", details="All required fields present."),
        ],
        approvals=[InvoiceApproval(reviewer="approver.rahul", decision="rejected",
                                   note="Third pallet not delivered per GRN-4410; ask vendor for revised invoice.")],
    )

    # 7) Scanned / unreadable PDF: kept, awaiting manual entry -------------
    inv7 = Invoice(
        vendor=blueriver, invoice_number=None, invoice_date=None,
        file_path="uploads/invoice_0007.pdf", original_filename="blueriver_scan_nov.pdf", file_size_bytes=812004,
        status="uploaded", is_verified=False, uploaded_by="clerk.anita",
        extraction_runs=[ExtractionRun(
            extracted_json=None, provider=SEED_PROVIDER, model_name=SEED_MODEL, status="no_text", duration_ms=95,
            error_message="PDF contains no extractable text (likely a scanned image). Manual entry required.")],
        checks=[InvoiceCheck(check_type="text_readable", result="fail",
                             details="No readable text found; OCR is out of scope. Enter fields manually.")],
    )

    session.add_all([inv3, inv4, inv5, inv6, inv7])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="drop all tables before creating them")
    parser.add_argument("--no-seed", action="store_true", help="do not insert sample data")
    args = parser.parse_args()

    if create_database_if_missing():
        print(f"Created database '{DB_NAME}'.")
    else:
        print(f"Database '{DB_NAME}' already exists.")
    print("Connected:", check_connection().split(",")[0])

    if args.reset:
        Base.metadata.drop_all(engine)
        print("Dropped all tables.")
    Base.metadata.create_all(engine)
    print("Tables ready:", ", ".join(sorted(Base.metadata.tables)))

    if args.no_seed:
        return
    with SessionLocal() as session:
        if session.scalar(select(func.count()).select_from(Vendor)):
            print("Data already present; skipping seed (use --reset to reseed).")
            return
        seed(session)
        session.commit()
        for table in Base.metadata.sorted_tables:
            count = session.scalar(select(func.count()).select_from(table))
            print(f"  {table.name:<20} {count} rows")
    print("Seed data inserted.")


if __name__ == "__main__":
    main()
