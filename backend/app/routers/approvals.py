
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pathlib import Path

UPLOAD_DIR = (
    Path(__file__).resolve().parents[2]
    / "uploads"
    / "invoices"
)

from app.db.database import get_connection_db
from app.routers.auth import require_role
from app.services.pdf_storage import load_invoice_pdf_for_viewing, inline_pdf_response
from app.schemas.approval import (
    ApprovalDecisionSubmit,
    ApprovalResponse
)


router = APIRouter(
    prefix="/approvals",
    tags=["Approvals"]
)


# =========================================================
# 1. GET ALL PENDING INVOICES
# =========================================================

@router.get("/")
def get_pending_invoices(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_role("approver"))
):

    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

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
                    uploaded_by_clerk_id,
                    created_at,
                    updated_at
                FROM invoices
                WHERE status = 'pending_approval'
                
                ORDER BY created_at ASC
                LIMIT %s OFFSET %s
                """,
                (limit, offset)
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

            return invoices

    finally:
        conn.close()


# =========================================================
# 2. GET COMPLETE INVOICE DETAILS
# =========================================================

@router.get("/{invoice_id}")
def get_invoice_for_approval(
    invoice_id: int,
    current_user: dict = Depends(require_role("approver"))
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
                AND status = 'pending_approval'
                """,
                (invoice_id,)
            )

            invoice_row = cursor.fetchone()

            if invoice_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Pending invoice not found"
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
            # STEP 3: Fetch invoice checks
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    check_id,
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

            return {
                "invoice": invoice,
                "items": items,
                "checks": checks
            }

    finally:
        conn.close()


# =========================================================
# 3. GET INVOICE CHECKS
# =========================================================

@router.get("/{invoice_id}/checks")
def get_invoice_checks(
    invoice_id: int,
    current_user: dict = Depends(require_role("approver"))
):

    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

            # -----------------------------------------
            # STEP 1: Verify invoice exists and is
            # pending approval
            # -----------------------------------------

            cursor.execute(
                """
                SELECT invoice_id
                FROM invoices
                WHERE invoice_id = %s
                AND status = 'pending_approval'
                """,
                (invoice_id,)
            )

            if cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Pending invoice not found"
                )

            # -----------------------------------------
            # STEP 2: Fetch all validation results
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

            rows = cursor.fetchall()

            columns = [
                description[0]
                for description in cursor.description
            ]

            checks = [
                dict(zip(columns, row))
                for row in rows
            ]

            return {
                "invoice_id": invoice_id,
                "total_checks": len(checks),
                "checks": checks
            }

    finally:
        conn.close()


# =========================================================
# 4. GET INVOICE HISTORY
# =========================================================

@router.get("/{invoice_id}/history")
def get_invoice_history(
    invoice_id: int,
    current_user: dict = Depends(require_role("approver"))
):

    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

            # -----------------------------------------
            # STEP 1: Verify invoice exists
            # -----------------------------------------

            cursor.execute(
                """
                SELECT invoice_id
                FROM invoices
                WHERE invoice_id = %s
                AND status = 'pending_approval'
                """,
                (invoice_id,)
            )

            if cursor.fetchone() is None:
                raise HTTPException(
                    status_code=404,
                    detail="Pending invoice not found"
                )

            # -----------------------------------------
            # STEP 2: Fetch clerk corrections
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
            # STEP 3: Fetch extraction history
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

            return {
                "invoice_id": invoice_id,
                "corrections": corrections,
                "extractions": extractions
            }

    finally:
        conn.close()

@router.post(
    "/{invoice_id}/decision",
    response_model=ApprovalResponse
)
def decide_invoice(
    invoice_id: int,
    request: ApprovalDecisionSubmit,
    current_user: dict = Depends(require_role("approver"))
):

    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

            # -----------------------------------------
            # STEP 1: Get authenticated approver ID
            # -----------------------------------------

            approver_id = current_user["id"]

            # -----------------------------------------
            # STEP 2: Fetch and lock invoice
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    invoice_id,
                    status,
                    duplicate_of_invoice_id
                FROM invoices
                WHERE invoice_id = %s
                FOR UPDATE
                """,
                (invoice_id,)
            )

            invoice = cursor.fetchone()

            if invoice is None:
                raise HTTPException(
                    status_code=404,
                    detail="Invoice not found"
                )

            _, status, duplicate_of = invoice

            # -----------------------------------------
            # STEP 3: Validate invoice status
            # -----------------------------------------

            if status != "pending_approval":
                raise HTTPException(
                    status_code=409,
                    detail=f"Invoice cannot be decided. Current status: {status}"
                )

            # if duplicate_of is not None:
            #     raise HTTPException(
            #         status_code=409,
            #         detail="Duplicate invoices cannot be approved or rejected"
            #     )
            decision = request.decision

            # Duplicate invoices cannot be approved.
            # However, approvers are allowed to reject them.

            if duplicate_of is not None and decision == "approved":
                raise HTTPException(
                    status_code=409,
                    detail="Duplicate invoices cannot be approved. Please reject this invoice."
                )

            # -----------------------------------------
            # STEP 4: Validate note
            # -----------------------------------------

            note = request.note.strip()

            if not note:
                raise HTTPException(
                    status_code=422,
                    detail="Approval note cannot be empty"
                )

            decision = request.decision

            # -----------------------------------------
            # STEP 5: Insert approval record
            # -----------------------------------------

            cursor.execute(
                """
                INSERT INTO invoice_approvals (
                    invoice_id,
                    approver_id,
                    decision,
                    note
                )
                VALUES (%s, %s, %s, %s)
                RETURNING
                    approval_id,
                    invoice_id,
                    approver_id,
                    decision,
                    note,
                    decided_at
                """,
                (
                    invoice_id,
                    approver_id,
                    decision,
                    note
                )
            )

            approval_row = cursor.fetchone()

            # -----------------------------------------
            # STEP 6: Update invoice status
            # -----------------------------------------

            cursor.execute(
                """
                UPDATE invoices
                SET
                    status = %s,
                    updated_at = NOW()
                WHERE invoice_id = %s
                """,
                (
                    decision,
                    invoice_id
                )
            )

            # -----------------------------------------
            # STEP 7: Commit transaction
            # -----------------------------------------

            conn.commit()

            # -----------------------------------------
            # STEP 8: Return approval response
            # -----------------------------------------

            return ApprovalResponse(
                approval_id=approval_row[0],
                invoice_id=approval_row[1],
                approver_id=approval_row[2],
                decision=approval_row[3],
                note=approval_row[4],
                decided_at=approval_row[5]
            )

    except HTTPException:
        conn.rollback()
        raise

    except Exception:
        conn.rollback()
        raise

    finally:
        conn.close()

def load_original_pdf(cursor, invoice_id: int) -> tuple[bytes, str] | None:

    cursor.execute(
        """
        SELECT original_file_location
        FROM invoice_original_files
        WHERE invoice_id = %s
        """,
        (invoice_id,)
    )

    row = cursor.fetchone()

    if not row:
        return None

    relative_path = row[0]

    # Resolve relative to backend directory
    backend_dir = Path(__file__).resolve().parents[2]

    file_path = (backend_dir / relative_path).resolve()

    # Ensure the resolved path stays inside the uploads directory
    if not file_path.is_relative_to(UPLOAD_DIR.resolve()):
        raise ValueError("Invalid original file location")

    if not file_path.is_file():
        return None

    return file_path.read_bytes(), file_path.name

from fastapi.responses import Response

@router.get("/{invoice_id}/original")
def download_original_invoice(
    invoice_id: int,
    current_user: dict = Depends(require_role("approver"))
):
    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:
            result = load_original_pdf(cursor, invoice_id)

        if result is None:
            raise HTTPException(
                status_code=404,
                detail="Original invoice PDF not found"
            )

        pdf_bytes, filename = result

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{filename}"' # For directly downloading the pdf
                    # f'inline; filename="{filename}"'   # For opening the pdf in new tab
            }
        )

    finally:
        conn.close()

@router.get("/{invoice_id}/pdf")
def view_invoice_pdf(
    invoice_id: int,
    current_user: dict = Depends(require_role("approver"))
):
    """Show the invoice PDF inline for invoices that have reached the approval stage."""
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
                raise HTTPException(status_code=404, detail="Invoice not found")
            result = load_invoice_pdf_for_viewing(cursor, invoice_id)
    finally:
        conn.close()

    if result is None:
        raise HTTPException(status_code=404, detail="Invoice PDF not found")
    return inline_pdf_response(*result)
