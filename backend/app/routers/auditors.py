
from typing import Optional, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.db.database import get_connection_db
from app.routers.auth import require_role
from app.services.pdf_storage import load_invoice_pdf_for_viewing, inline_pdf_response

from app.schemas.auditor import (
    AuditorInvoiceResponse,
    AuditorInvoiceListResponse,
    AuditorInvoiceFullDetailsResponse
)


router = APIRouter(
    prefix="/auditor",
    tags=["Auditor"]
)


# =========================================================
# 1. GET ALL AUDITABLE INVOICES
# =========================================================

@router.get(
    "/invoices",
    response_model=AuditorInvoiceListResponse
)
def get_auditor_invoices(
    status: Optional[
        Literal["pending_approval", "approved", "rejected"]
    ] = Query(default=None),

    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),

    current_user: dict = Depends(require_role("auditor"))
):

    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

            # -----------------------------------------
            # STEP 1: Count total matching invoices
            # -----------------------------------------

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM invoices
                WHERE status IN (
                    'pending_approval',
                    'approved',
                    'rejected'
                )
                AND (%s IS NULL OR status = %s)
                """,
                (status, status)
            )

            total = cursor.fetchone()[0]

            # -----------------------------------------
            # STEP 2: Fetch invoices
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    invoice_id,
                    vendor_id,
                    invoice_number,
                    invoice_date,
                    due_date,
                    currency,
                    subtotal,
                    tax_amount,
                    total_amount,
                    original_filename,
                    file_size_bytes,
                    status,
                    is_verified,
                    duplicate_of_invoice_id,
                    uploaded_by_clerk_id,
                    created_at,
                    updated_at
                FROM invoices
                WHERE status IN (
                    'pending_approval',
                    'approved',
                    'rejected'
                )
                AND (%s IS NULL OR status = %s)
                ORDER BY created_at DESC
                LIMIT %s OFFSET %s
                """,
                (status, status, limit, offset)
            )

            rows = cursor.fetchall()

            columns = [
                description[0]
                for description in cursor.description
            ]

            invoices = [
                dict(zip(columns, row))
                for row in rows
            ]

            # -----------------------------------------
            # STEP 3: Return response
            # -----------------------------------------

            return {
                "total": total,
                "limit": limit,
                "offset": offset,
                "invoices": invoices
            }

    finally:
        conn.close()

@router.get(
    "/invoices/{invoice_id}",
    response_model=AuditorInvoiceFullDetailsResponse
)
def get_auditor_invoice_details(
    invoice_id: int,
    current_user: dict = Depends(require_role("auditor"))
):

    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

            # -----------------------------------------
            # STEP 1: Fetch invoice details
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    invoice_id,
                    vendor_id,
                    invoice_number,
                    invoice_date,
                    due_date,
                    currency,
                    subtotal,
                    tax_amount,
                    total_amount,
                    original_filename,
                    file_size_bytes,
                    status,
                    is_verified,
                    duplicate_of_invoice_id,
                    uploaded_by_clerk_id,
                    created_at,
                    updated_at
                FROM invoices
                WHERE invoice_id = %s
                AND status IN (
                    'pending_approval',
                    'approved',
                    'rejected'
                )
                """,
                (invoice_id,)
            )

            invoice_row = cursor.fetchone()

            if invoice_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Auditable invoice not found"
                )

            invoice_columns = [
                description[0]
                for description in cursor.description
            ]

            invoice = dict(
                zip(invoice_columns, invoice_row)
            )

            # -----------------------------------------
            # STEP 2: Fetch invoice line items
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    item_id,
                    invoice_id,
                    line_no,
                    item_name,
                    quantity,
                    unit_price,
                    line_total,
                    source
                FROM invoice_items
                WHERE invoice_id = %s
                ORDER BY line_no ASC
                """,
                (invoice_id,)
            )

            item_rows = cursor.fetchall()

            item_columns = [
                description[0]
                for description in cursor.description
            ]

            items = [
                dict(zip(item_columns, row))
                for row in item_rows
            ]

            # -----------------------------------------
            # STEP 3: Fetch invoice validation checks
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    check_id,
                    invoice_id,
                    check_type,
                    result,
                    details,
                    checked_at
                FROM invoice_checks
                WHERE invoice_id = %s
                ORDER BY checked_at DESC
                """,
                (invoice_id,)
            )

            check_rows = cursor.fetchall()

            check_columns = [
                description[0]
                for description in cursor.description
            ]

            checks = [
                dict(zip(check_columns, row))
                for row in check_rows
            ]

            # -----------------------------------------
            # STEP 4: Fetch clerk correction history
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    correction_id,
                    field_name,
                    old_value,
                    new_value,
                    clerk_id,
                    corrected_at
                FROM invoice_corrections
                WHERE invoice_id = %s
                ORDER BY corrected_at ASC
                """,
                (invoice_id,)
            )

            correction_rows = cursor.fetchall()

            correction_columns = [
                description[0]
                for description in cursor.description
            ]

            corrections = [
                dict(zip(correction_columns, row))
                for row in correction_rows
            ]

            # -----------------------------------------
            # STEP 5: Fetch AI extraction history
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    run_id,
                    extracted_json,
                    ai_summary,
                    provider,
                    model_name,
                    status,
                    error_message,
                    duration_ms,
                    created_at
                FROM extraction_runs
                WHERE invoice_id = %s
                ORDER BY created_at ASC
                """,
                (invoice_id,)
            )

            extraction_rows = cursor.fetchall()

            extraction_columns = [
                description[0]
                for description in cursor.description
            ]

            extractions = [
                dict(zip(extraction_columns, row))
                for row in extraction_rows
            ]

            # -----------------------------------------
            # STEP 6: Fetch approval history
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    approval_id,
                    approver_id,
                    decision,
                    note,
                    decided_at
                FROM invoice_approvals
                WHERE invoice_id = %s
                ORDER BY decided_at ASC
                """,
                (invoice_id,)
            )

            approval_rows = cursor.fetchall()

            approval_columns = [
                description[0]
                for description in cursor.description
            ]

            approvals = [
                dict(zip(approval_columns, row))
                for row in approval_rows
            ]

            # -----------------------------------------
            # STEP 7: Return complete invoice details
            # -----------------------------------------

            return {
                "invoice": invoice,
                "items": items,
                "checks": checks,
                "corrections": corrections,
                "extractions": extractions,
                "approvals": approvals
            }

    finally:
        conn.close()


@router.get("/invoices/{invoice_id}/pdf")
def view_auditor_invoice_pdf(
    invoice_id: int,
    current_user: dict = Depends(require_role("auditor"))
):
    """Show the invoice PDF inline for auditable invoices."""
    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM invoices
                WHERE invoice_id = %s
                AND status IN ('pending_approval', 'approved', 'rejected')
                """,
                (invoice_id,),
            )
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail="Auditable invoice not found")
            result = load_invoice_pdf_for_viewing(cursor, invoice_id)
    finally:
        conn.close()

    if result is None:
        raise HTTPException(status_code=404, detail="Invoice PDF not found")
    return inline_pdf_response(*result)
