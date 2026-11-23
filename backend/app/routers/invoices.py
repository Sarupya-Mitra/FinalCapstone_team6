from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile,File,Form
from typing import Optional
from pathlib import Path
import uuid
from pydantic import BaseModel, ConfigDict, Field, ValidationError
import fitz
import time,json
from decimal import Decimal
from psycopg2 import IntegrityError
from psycopg2.errors import UniqueViolation

from app.schemas.invoice import (InvoiceResponse,InvoiceSubmit,InvoiceExtractionResult,InvoiceReviewResponse,
                                 InvoiceCorrectionSubmit)
from app.db.database import get_connection_db
from app.routers.auth import require_role
from app.core.config import UPLOAD_DIR,MAX_FILE_SIZE,ALLOWED_EXTENSIONS,BASE_DIR
from app.services.pdf_storage import compress_pdf, upload_pdf, load_pdf
from agent import (your_ai_agent, review_invoice_with_ai, AIAgentError,
                   AI_PROVIDER, AI_MODEL)

# invoices.file_path value for PDFs stored in the invoice_files table
DB_FILE_PREFIX = "db://invoice_files/"

router = APIRouter(
    prefix="/invoices",
    tags=['Invoices']
)
# The following endpoint can be used as:
# all vendors: GET /invoices
# or filter by vendor: GET/invoices?vendor_id=1
# or filter by status: GET/invoices?status=pending_approval
# or combine filters: GET /invoices?vendor_id=1&status=uploaded
# also pagination is present: GET /invoices?limit=20&offset=0
@router.get("/", response_model=list[InvoiceResponse])
def get_invoices(
    vendor_id: Optional[int] = None,
    status:Optional[str] = None,
    limit:int = Query(default=50,ge=1,le=100),
    offset: int = Query(default=0, ge=0),
    current_user: dict = Depends(require_role("clerk")),
):
    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:
            query = """
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
                WHERE 1=1"""
            params = []
            # Clerk ownership filter (Show only invoices uploaded by this particular clerk)
            query += " AND uploaded_by_clerk_id = %s"
            params.append(current_user["id"])
            if vendor_id is not None:
                query += " AND vendor_id = %s"
                params.append(vendor_id)
            if status is not None:
                query += " AND status = %s"
                params.append(status)
            query += """
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s"""
            params.extend([limit,offset])
            cursor.execute(query,tuple(params))

            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
            invoices = [
                dict(zip(columns, row))
                for row in rows
            ]

            return invoices
    finally:
        conn.close()

# The following endpoint is only for:
# getting a particular invoice by its invoice_id and also the clerk who has uploaded it can get that invoice
@router.get("/{invoice_id}", response_model=InvoiceResponse)
def get_invoice(
    invoice_id: int,
    current_user: dict = Depends(require_role("clerk"))
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
                    duplicate_of_invoice_id,
                    uploaded_by_clerk_id,
                    created_at,
                    updated_at
                FROM invoices
                WHERE invoice_id = %s
                AND uploaded_by_clerk_id = %s
                """,
                (invoice_id,current_user["id"],)
            )

            row = cursor.fetchone()

            if row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Invoice not found"
                )

            columns = [desc[0] for desc in cursor.description]

            return dict(zip(columns, row))

    finally:
        conn.close()

@router.post("/", response_model=InvoiceResponse)
def upload_invoice(
        vendor_id: int = Form(...),
        file: UploadFile = File(...),
        current_user: dict = Depends(require_role("clerk"))
):
    try:
        # Validate filename
        original_filename = Path(file.filename or "").name
        if not original_filename:
            raise HTTPException(
                status_code=400,
                detail="Filename is required"
            )
        # Validate file extension
        extension = Path(original_filename).suffix.lower()

        if extension not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Only PDF files are allowed"
            )

        # Read the upload into memory, refusing anything over MAX_FILE_SIZE
        # (the raw upload limit; the stored, compressed copy must be <= 1 MB).
        raw = file.file.read(MAX_FILE_SIZE + 1)
        if len(raw) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=413,
                detail="File size exceeds the limit"
            )
        # Validate file is not empty
        if not raw:
            raise HTTPException(
                status_code=400,
                detail = "Uploaded File is empty"
            )
        # Verify PDF signature
        if not raw.startswith(b"%PDF-"):
            raise HTTPException(
                status_code=400,
                detail="Invalid PDF file"
            )

        # Compress with PyMuPDF; raises 413 if it can't get under 1 MB
        compressed = compress_pdf(raw)

        clerk_id = current_user["id"]
        conn = get_connection_db()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO invoices (
                    vendor_id,
                    file_path,
                    original_filename,
                    file_size_bytes,
                    uploaded_by_clerk_id)
                    VALUES (%s,%s,%s,%s,%s)
                    RETURNING
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
                        updated_at""",
                    (
                        vendor_id,
                        # PDF lives in invoice_files; file_path is just a reference
                        f"{DB_FILE_PREFIX}{uuid.uuid4()}.pdf",
                        original_filename,
                        compressed.stored_size,
                        clerk_id
                    )
                )
                row = cursor.fetchone()
                columns = [
                    description[0]
                    for description in cursor.description
                ]

                invoice = dict(zip(columns, row))

                # Store the compressed PDF in the same transaction
                upload_pdf(cursor, invoice["invoice_id"], original_filename, compressed)

                conn.commit()

                return invoice
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    finally:
        file.file.close()

###########################################################
# Extracting the pdf
###########################################################
def extract_text_from_pdf(source: Path | bytes) -> str:

    try:
        pdf_doc = (
            fitz.open(stream=source, filetype="pdf")
            if isinstance(source, (bytes, bytearray))
            else fitz.open(source)
        )
        with pdf_doc as pdf:

            extracted_text = []

            for page in pdf:
                text = page.get_text("text")
                if text:
                    extracted_text.append(text)

            return "\n".join(extracted_text).strip()

    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Unable to read PDF: {str(e)}"
        )

def validate_ai_output(ai_result: dict) -> InvoiceExtractionResult:
    try:
        validated_result = InvoiceExtractionResult.model_validate(
            ai_result
        )
        return validated_result
    except ValidationError as e:
        raise ValueError(
            f"AI output validation failed: {e}"
        )

def update_invoices_table(
    cursor,
    invoice_id: int,
    validated_result: InvoiceExtractionResult
):

    cursor.execute(
        """
        UPDATE invoices
        SET
            invoice_number = %s,
            invoice_date = %s,
            due_date = %s,
            currency = %s,
            subtotal = %s,
            tax_amount = %s,
            total_amount = %s,
            status = 'extracted',
            updated_at = NOW()
        WHERE invoice_id = %s
        """,
        (
            validated_result.invoice_number,
            validated_result.invoice_date,
            validated_result.due_date,
            validated_result.currency,
            validated_result.subtotal,
            validated_result.tax_amount,
            validated_result.total_amount,
            invoice_id
        )
    )

    if cursor.rowcount != 1:
        raise ValueError(
            "Invoice could not be updated"
        )

def insert_into_invoice_items_table(
    cursor,
    invoice_id: int,
    validated_result: InvoiceExtractionResult
):

    for item in validated_result.items:
        cursor.execute(
            """
            INSERT INTO invoice_items (
                invoice_id,
                line_no,
                item_name,
                quantity,
                unit_price,
                line_total,
                source
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                invoice_id,
                item.line_no,
                item.item_name,
                item.quantity,
                item.unit_price,
                item.line_total,
                "ai"
            )
        )
def insert_extraction_run(
    cursor,
    invoice_id: int,
    extracted_json: dict | None,
    status: str,
    error_message: str | None = None,
    provider: str | None = None,
    model_name: str | None = None,
    duration_ms: int | None = None
):

    cursor.execute(
        """
        INSERT INTO extraction_runs (
            invoice_id,
            extracted_json,
            provider,
            model_name,
            status,
            error_message,
            duration_ms
        )
        VALUES (%s, %s::jsonb, %s, %s, %s, %s, %s)
        """,
        (
            invoice_id,
            json.dumps(extracted_json) if extracted_json is not None else None,
            provider,
            model_name,
            status,
            error_message,
            duration_ms
        )
    )

@router.post("/{invoice_id}/extract")
def extract_invoice(
    invoice_id: int,
    current_user: dict = Depends(require_role("clerk"))
):

    start_time = time.time()
    conn = get_connection_db()
    try:
        with conn.cursor() as cursor:
            # ----------------------------------
            # STEP 1: Check whether invoice exists
            # ----------------------------------
            cursor.execute(
                """
                SELECT
                    invoice_id,
                    file_path,
                    status
                FROM invoices
                WHERE invoice_id = %s
                """,
                (invoice_id,)
            )
            invoice = cursor.fetchone()
            if invoice is None:
                raise HTTPException(
                    status_code=404,
                    detail="Invoice not found"
                )
            stored_file_path = invoice[1]
            invoice_status = invoice[2]

            # ----------------------------------
            # STEP 2: Check invoice status
            # ----------------------------------

            if invoice_status not in ("uploaded", "extracted"):
                raise HTTPException(
                    status_code=400,
                    detail="Invoice cannot be extracted in its current status"
                )

            # ----------------------------------
            # STEP 3: Load the stored PDF
            # (invoice_files in the DB; older invoices may still be on disk)
            # ----------------------------------

            pdf_source = load_pdf(cursor, invoice_id)

            if pdf_source is None:
                file_path = (BASE_DIR / stored_file_path).resolve()

                # Prevent paths outside the upload directory
                if not file_path.is_relative_to(UPLOAD_DIR.resolve()):
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid invoice file path"
                    )

                if not file_path.is_file():
                    raise HTTPException(
                        status_code=404,
                        detail="Invoice PDF file not found"
                    )
                pdf_source = file_path

            # ----------------------------------
            # STEP 4: Extract text using PyMuPDF
            # ----------------------------------

            extracted_text = extract_text_from_pdf(pdf_source)

            duration_ms = int(
                (time.time() - start_time) * 1000
            )

            if not extracted_text:

                cursor.execute(
                    """
                    INSERT INTO extraction_runs (
                        invoice_id,
                        extracted_json,
                        status,
                        error_message,
                        duration_ms
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        invoice_id,
                        None,
                        "no_text",
                        "No readable text found in PDF",
                        duration_ms
                    )
                )

                conn.commit()

                return {
                    "message": "No readable text found in PDF",
                    "invoice_id": invoice_id,
                    "status": "no_text"
                }

            # ----------------------------------
            # STEP 5: AI AGENT INTEGRATION
            # ----------------------------------

            # The agent (backend/agent) returns:
            # {
            #     "invoice_number": "INV-001",
            #     "invoice_date": "2026-11-15",
            #     "due_date": "2026-12-15",
            #     "currency": "USD",
            #     "subtotal": 1000.00,
            #     "tax_amount": 100.00,
            #     "total_amount": 1100.00,
            #     "items": [...]
            # }
            # If the model is unavailable, the invoice is preserved and the
            # failed run is logged so the clerk can proceed manually.

            try:
                ai_result = your_ai_agent(extracted_text)
            except AIAgentError as e:
                insert_extraction_run(
                    cursor=cursor,
                    invoice_id=invoice_id,
                    extracted_json=None,
                    status=e.run_status,
                    error_message=str(e),
                    provider=AI_PROVIDER,
                    model_name=AI_MODEL,
                    duration_ms=int((time.time() - start_time) * 1000)
                )

                conn.commit()

                return {
                    "message": f"AI extraction unavailable: {e}. "
                               "The invoice is preserved for manual entry.",
                    "invoice_id": invoice_id,
                    "status": e.run_status
                }

            ## ----------------------------------
            ## STEP 6: VALIDATE AI OUTPUT
            ## ----------------------------------

            validated_result = validate_ai_output(ai_result)

            # ----------------------------------
            # STEP 7: UPDATE INVOICES TABLE
            # ----------------------------------

            update_invoices_table(
                cursor,
                invoice_id,
                validated_result
            )

            # ----------------------------------
            # STEP 8: INSERT INVOICE ITEMS
            # ----------------------------------

            insert_into_invoice_items_table(
                cursor,
                invoice_id,
                validated_result
            )

            # ----------------------------------
            # STEP 9: RECORD SUCCESSFUL EXTRACTION
            # ----------------------------------

            duration_ms = int(
                (time.time() - start_time) * 1000
            )

            extracted_json = validated_result.model_dump(mode="json")

            insert_extraction_run(
                cursor=cursor,
                invoice_id=invoice_id,
                extracted_json=extracted_json,
                status="success",
                provider=AI_PROVIDER,
                model_name=AI_MODEL,
                duration_ms=duration_ms
            )

            conn.commit()

            return {
                "message": "Invoice extracted successfully",
                "invoice_id": invoice_id,
                "status": "success",
                "extracted_data": extracted_json
            }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()
        print("Error:", e)
        raise HTTPException(
            status_code=500,
            detail="Invoice extraction failed"
        )

    finally:
        conn.close()

#############################
## Getting the updated and inserted data result from extraction_runs, invoice_items and invoice tables
## Basically the data which was populated due to an pdf being uploaded, so we will use this when clerk has already uploaded
## the pdf and then he needs to validate or correct the extracted data.
#############################

@router.get("/{invoice_id}/review", response_model=InvoiceReviewResponse)
def get_invoice_for_review(
    invoice_id: int,
    current_user: dict = Depends(require_role("clerk"))
):
    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

            # STEP 1: Fetch invoice and verify ownership
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
                  AND uploaded_by_clerk_id = %s
                """,
                (invoice_id, current_user["id"])
            )

            invoice_row = cursor.fetchone()

            if invoice_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Invoice not found"
                )

            columns = [desc[0] for desc in cursor.description]
            invoice = dict(zip(columns, invoice_row))

            # STEP 2: Fetch invoice items
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
                ORDER BY line_no
                """,
                (invoice_id,)
            )

            item_rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]

            items = [
                dict(zip(columns, row))
                for row in item_rows
            ]

            # STEP 3: Fetch latest extraction run
            cursor.execute(
                """
                SELECT
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
                ORDER BY created_at DESC, run_id DESC
                LIMIT 1
                """,
                (invoice_id,)
            )

            extraction_row = cursor.fetchone()

            extraction = None

            if extraction_row is not None:
                columns = [
                    desc[0]
                    for desc in cursor.description
                ]

                extraction = dict(
                    zip(columns, extraction_row)
                )

            return {
                "invoice": invoice,
                "items": items,
                "extraction": extraction
            }

    finally:
        conn.close()

########################
## Helper function for inserting to invoice_corrections after clerk has corrected it.
########################
def record_invoice_correction(
    cursor,
    invoice_id: int,
    field_name: str,
    old_value,
    new_value,
    clerk_id: int
):
    cursor.execute(
        """
        INSERT INTO invoice_corrections (
            invoice_id,
            field_name,
            old_value,
            new_value,
            clerk_id
        )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            invoice_id,
            field_name,
            str(old_value) if old_value is not None else None,
            str(new_value) if new_value is not None else None,
            clerk_id
        )
    )
###################
## Actual endpoint after clerk has corrected and validated.
###################
@router.put("/{invoice_id}/review")
def correct_invoice(
    invoice_id: int,
    correction: InvoiceCorrectionSubmit,
    current_user: dict = Depends(require_role("clerk"))
):
    """
    Allows a clerk to correct AI-extracted invoice information.

    The endpoint:
    1. Verifies invoice ownership.
    2. Checks invoice status.
    3. Compares invoice header fields.
    4. Records header corrections.
    5. Updates existing line items.
    6. Inserts newly added line items.
    7. Records deleted line items.
    8. Commits all changes in one transaction.

    This endpoint does NOT submit the invoice for approval.
    """

    clerk_id = current_user["id"]

    # ------------------------------------------------
    # STEP 1: Validate submitted line items
    # ------------------------------------------------

    line_numbers = [
        item.line_no for item in correction.items
    ]

    if len(line_numbers) != len(set(line_numbers)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate line numbers are not allowed"
        )

    item_ids = [
        item.item_id
        for item in correction.items
        if item.item_id is not None
    ]

    if len(item_ids) != len(set(item_ids)):
        raise HTTPException(
            status_code=400,
            detail="Duplicate item IDs are not allowed"
        )

    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

            # --------------------------------------------
            # STEP 2: Fetch invoice and verify ownership
            # --------------------------------------------

            # FOR UPDATE locks this invoice row until
            # the transaction commits or rolls back.

            cursor.execute(
                """
                SELECT
                    invoice_id,
                    invoice_number,
                    invoice_date,
                    due_date,
                    currency,
                    subtotal,
                    tax_amount,
                    total_amount,
                    status
                FROM invoices
                WHERE invoice_id = %s
                  AND uploaded_by_clerk_id = %s
                FOR UPDATE
                """,
                (invoice_id, clerk_id)
            )

            invoice_row = cursor.fetchone()

            if invoice_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Invoice not found"
                )

            columns = [
                desc[0] for desc in cursor.description
            ]

            existing_invoice = dict(
                zip(columns, invoice_row)
            )

            # --------------------------------------------
            # STEP 3: Validate invoice status
            # --------------------------------------------

            if existing_invoice["status"] != "extracted":
                raise HTTPException(
                    status_code=400,
                    detail="Only extracted invoices can be corrected"
                )

            # --------------------------------------------
            # STEP 4: Compare invoice header fields
            # --------------------------------------------

            header_fields = [
                "invoice_number",
                "invoice_date",
                "due_date",
                "currency",
                "subtotal",
                "tax_amount",
                "total_amount"
            ]

            for field in header_fields:

                old_value = existing_invoice[field]
                new_value = getattr(correction, field)

                if old_value != new_value:

                    record_invoice_correction(
                        cursor=cursor,
                        invoice_id=invoice_id,
                        field_name=field,
                        old_value=old_value,
                        new_value=new_value,
                        clerk_id=clerk_id
                    )

            # --------------------------------------------
            # STEP 5: Update invoices table
            # --------------------------------------------

            cursor.execute(
                """
                UPDATE invoices
                SET
                    invoice_number = %s,
                    invoice_date = %s,
                    due_date = %s,
                    currency = %s,
                    subtotal = %s,
                    tax_amount = %s,
                    total_amount = %s,
                    updated_at = NOW()
                WHERE invoice_id = %s
                """,
                (
                    correction.invoice_number,
                    correction.invoice_date,
                    correction.due_date,
                    correction.currency,
                    correction.subtotal,
                    correction.tax_amount,
                    correction.total_amount,
                    invoice_id
                )
            )

            # --------------------------------------------
            # STEP 6: Fetch existing invoice items
            # --------------------------------------------

            cursor.execute(
                """
                SELECT
                    item_id,
                    line_no,
                    item_name,
                    quantity,
                    unit_price,
                    line_total,
                    source
                FROM invoice_items
                WHERE invoice_id = %s
                FOR UPDATE
                """,
                (invoice_id,)
            )

            existing_item_rows = cursor.fetchall()

            columns = [
                desc[0] for desc in cursor.description
            ]

            existing_items = {
                row[0]: dict(zip(columns, row))
                for row in existing_item_rows
            }

            # Keep track of existing items submitted
            # by the clerk.
            submitted_item_ids = set()

            # --------------------------------------------
            # STEP 7: Process submitted line items
            # --------------------------------------------

            for item in correction.items:

                # ========================================
                # CASE A: Existing line item
                # ========================================

                if item.item_id is not None:

                    # Make sure the item belongs to
                    # this particular invoice.

                    if item.item_id not in existing_items:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"Invalid item_id: {item.item_id}. "
                                "Item does not belong to this invoice."
                            )
                        )

                    submitted_item_ids.add(item.item_id)

                    old_item = existing_items[item.item_id]

                    item_fields = [
                        "line_no",
                        "item_name",
                        "quantity",
                        "unit_price",
                        "line_total"
                    ]

                    changed = False

                    # Compare every field individually.
                    for field in item_fields:

                        old_value = old_item[field]
                        new_value = getattr(item, field)

                        if old_value != new_value:

                            record_invoice_correction(
                                cursor=cursor,
                                invoice_id=invoice_id,
                                field_name=(
                                    f"items[{item.item_id}].{field}"
                                ),
                                old_value=old_value,
                                new_value=new_value,
                                clerk_id=clerk_id
                            )

                            changed = True

                    # Update only if something changed.
                    if changed:

                        cursor.execute(
                            """
                            UPDATE invoice_items
                            SET
                                line_no = %s,
                                item_name = %s,
                                quantity = %s,
                                unit_price = %s,
                                line_total = %s,
                                source = 'manual'
                            WHERE item_id = %s
                              AND invoice_id = %s
                            """,
                            (
                                item.line_no,
                                item.item_name,
                                item.quantity,
                                item.unit_price,
                                item.line_total,
                                item.item_id,
                                invoice_id
                            )
                        )

                # ========================================
                # CASE B: Newly added line item
                # ========================================

                else:

                    cursor.execute(
                        """
                        INSERT INTO invoice_items (
                            invoice_id,
                            line_no,
                            item_name,
                            quantity,
                            unit_price,
                            line_total,
                            source
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'manual')
                        RETURNING item_id
                        """,
                        (
                            invoice_id,
                            item.line_no,
                            item.item_name,
                            item.quantity,
                            item.unit_price,
                            item.line_total
                        )
                    )

                    new_item_id = cursor.fetchone()[0]

                    # Store the complete newly added item
                    # as JSON in the correction history.

                    new_item_data = {
                        "line_no": item.line_no,
                        "item_name": item.item_name,
                        "quantity": str(item.quantity),
                        "unit_price": str(item.unit_price),
                        "line_total": (
                            str(item.line_total)
                            if item.line_total is not None
                            else None
                        )
                    }

                    record_invoice_correction(
                        cursor=cursor,
                        invoice_id=invoice_id,
                        field_name=f"items[{new_item_id}]",
                        old_value=None,
                        new_value=json.dumps(new_item_data),
                        clerk_id=clerk_id
                    )

            # --------------------------------------------
            # STEP 8: Identify deleted line items
            # --------------------------------------------

            # If an existing item was not included in
            # the clerk's submitted list, it was removed.

            for existing_item_id, old_item in existing_items.items():

                if existing_item_id not in submitted_item_ids:

                    old_item_data = {
                        "line_no": old_item["line_no"],
                        "item_name": old_item["item_name"],
                        "quantity": str(old_item["quantity"]),
                        "unit_price": str(old_item["unit_price"]),
                        "line_total": (
                            str(old_item["line_total"])
                            if old_item["line_total"] is not None
                            else None
                        )
                    }

                    # Record the deleted item's old data
                    # before actually deleting it.

                    record_invoice_correction(
                        cursor=cursor,
                        invoice_id=invoice_id,
                        field_name=f"items[{existing_item_id}]",
                        old_value=json.dumps(old_item_data),
                        new_value=None,
                        clerk_id=clerk_id
                    )

                    cursor.execute(
                        """
                        DELETE FROM invoice_items
                        WHERE item_id = %s
                          AND invoice_id = %s
                        """,
                        (existing_item_id, invoice_id)
                    )

            # --------------------------------------------
            # STEP 9: Commit transaction
            # --------------------------------------------

            conn.commit()

            return {
                "message": "Invoice corrections saved successfully",
                "invoice_id": invoice_id,
                "status": "extracted"
            }

    except HTTPException:
        conn.rollback()
        raise

    except UniqueViolation:
        conn.rollback()

        raise HTTPException(
            status_code=409,
            detail=(
                "An invoice with this invoice number "
                "already exists for this vendor."
            )
        )

    except Exception as e:
        conn.rollback()

        print("Invoice correction error:", e)

        raise HTTPException(
            status_code=500,
            detail="Unable to save invoice corrections"
        )

    finally:
        conn.close()

###################################
## Deterministic checks before final clerk submission
###################################
def run_deterministic_checks(invoice, items):
    """
    Performs basic deterministic invoice validations.

    Returns a list of check results.
    """

    checks = []

    # -----------------------------------------
    # CHECK 1: Missing required fields
    # -----------------------------------------

    required_fields = [
        "invoice_number",
        "invoice_date",
        "due_date",
        "subtotal",
        "tax_amount",
        "total_amount"
    ]

    missing_fields = [
        field
        for field in required_fields
        if invoice[field] is None
    ]

    checks.append({
        "check_type": "missing_field",
        "result": "fail" if missing_fields else "pass",
        "details": (
            f"Missing fields: {', '.join(missing_fields)}"
            if missing_fields
            else "All required invoice fields are present."
        )
    })

    # -----------------------------------------
    # CHECK 2: Line total verification
    # -----------------------------------------

    incorrect_items = []

    for item in items:

        expected_total = (
            item["quantity"] * item["unit_price"]
        )

        actual_total = item["line_total"]

        if (
            actual_total is None
            or abs(expected_total - actual_total) > Decimal("0.01")
        ):
            incorrect_items.append(item["line_no"])

    checks.append({
        "check_type": "line_total",
        "result": "fail" if incorrect_items else "pass",
        "details": (
            f"Incorrect line totals for lines: {incorrect_items}"
            if incorrect_items
            else "All line totals are correct."
        )
    })

    # -----------------------------------------
    # CHECK 3: Invoice total verification
    # -----------------------------------------

    expected_invoice_total = (
        (invoice["subtotal"] or Decimal("0"))
        + (invoice["tax_amount"] or Decimal("0"))
    )

    actual_invoice_total = invoice["total_amount"]

    invoice_total_correct = (
        actual_invoice_total is not None
        and abs(
            expected_invoice_total - actual_invoice_total
        ) <= Decimal("0.01")
    )

    checks.append({
        "check_type": "invoice_total",
        "result": "pass" if invoice_total_correct else "fail",
        "details": (
            "Invoice total matches subtotal plus tax."
            if invoice_total_correct
            else "Invoice total does not match subtotal plus tax."
        )
    })

    # -----------------------------------------
    # CHECK 4: Duplicate invoice verification
    # -----------------------------------------

    is_duplicate = (
        invoice["duplicate_of_invoice_id"] is not None
    )

    checks.append({
        "check_type": "duplicate",
        "result": "fail" if is_duplicate else "pass",
        "details": (
            f"Possible duplicate of invoice "
            f"{invoice['duplicate_of_invoice_id']}."
            if is_duplicate
            else "No duplicate invoice has been identified."
        )
    })

    # -----------------------------------------
    # CHECK 5: PDF text readability
    # -----------------------------------------

    checks.append({
        "check_type": "text_readable",
        "result": "pass",
        "details": "PDF text was successfully extracted."
    })

    return checks

def run_ai_invoice_checks(invoice, items):
    """
    Advisory AI review of the invoice (backend/agent).

    Return format:

    [
        {
            "check_type": "missing_field",
            "result": "pass",
            "details": "..."
        },
        ...
    ]

    AI findings are advisory ("fail" is downgraded to "warning").
    If the model is unavailable, no AI checks are added so that
    submission still works on the deterministic checks alone.
    """

    try:
        return review_invoice_with_ai(invoice, items)
    except AIAgentError as e:
        print(f"AI invoice checks skipped ({e.run_status}): {e}")
        return []


@router.post("/{invoice_id}/submit")
def submit_invoice(
    invoice_id: int,
    current_user: dict = Depends(require_role("clerk"))
):
    """
    Submits a corrected invoice for approval.

    Workflow:
    1. Verify invoice ownership.
    2. Verify invoice status.
    3. Fetch invoice and line items.
    4. Run deterministic checks.
    5. Run AI checks.
    6. Store all check results.
    7. Change status based on validation results.

    All database modifications happen in one transaction.
    """

    clerk_id = current_user["id"]

    conn = get_connection_db()

    try:
        with conn.cursor() as cursor:

            # -----------------------------------------
            # STEP 1: Fetch invoice and lock its row
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
                    duplicate_of_invoice_id,
                    status
                FROM invoices
                WHERE invoice_id = %s
                  AND uploaded_by_clerk_id = %s
                FOR UPDATE
                """,
                (invoice_id, clerk_id)
            )

            invoice_row = cursor.fetchone()

            if invoice_row is None:
                raise HTTPException(
                    status_code=404,
                    detail="Invoice not found"
                )

            columns = [
                desc[0] for desc in cursor.description
            ]

            invoice = dict(
                zip(columns, invoice_row)
            )

            # -----------------------------------------
            # STEP 2: Verify invoice status
            # -----------------------------------------

            if invoice["status"] != "extracted":
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Only extracted invoices can "
                        "be submitted for approval"
                    )
                )

            # -----------------------------------------
            # STEP 3: Fetch invoice line items
            # -----------------------------------------

            cursor.execute(
                """
                SELECT
                    item_id,
                    line_no,
                    item_name,
                    quantity,
                    unit_price,
                    line_total
                FROM invoice_items
                WHERE invoice_id = %s
                ORDER BY line_no ASC
                """,
                (invoice_id,)
            )

            item_rows = cursor.fetchall()

            item_columns = [
                desc[0] for desc in cursor.description
            ]

            items = [
                dict(zip(item_columns, row))
                for row in item_rows
            ]

            # -----------------------------------------
            # STEP 4: Run deterministic checks
            # -----------------------------------------

            deterministic_results = run_deterministic_checks(
                invoice,
                items
            )

            # -----------------------------------------
            # STEP 5: Run AI checks
            # -----------------------------------------

            ai_results = run_ai_invoice_checks(
                invoice,
                items
            )

            # -----------------------------------------
            # STEP 6: Combine all check results
            # -----------------------------------------

            all_checks = (
                deterministic_results + ai_results
            )

            # -----------------------------------------
            # STEP 7: Validate AI/check output
            # -----------------------------------------

            allowed_types = {
                "duplicate",
                "line_total",
                "invoice_total",
                "missing_field",
                "text_readable"
            }

            allowed_results = {
                "pass",
                "fail",
                "warning"
            }

            for check in all_checks:

                if check["check_type"] not in allowed_types:
                    raise ValueError(
                        "Invalid invoice check type"
                    )

                if check["result"] not in allowed_results:
                    raise ValueError(
                        "Invalid invoice check result"
                    )

                if not isinstance(check.get("details"), str):
                    raise ValueError(
                        "Check details must be a string"
                    )

            # -----------------------------------------
            # STEP 8: Store checks in invoice_checks
            # -----------------------------------------

            for check in all_checks:

                cursor.execute(
                    """
                    INSERT INTO invoice_checks (
                        invoice_id,
                        check_type,
                        result,
                        details
                    )
                    VALUES (%s, %s, %s, %s)
                    """,
                    (
                        invoice_id,
                        check["check_type"],
                        check["result"],
                        check["details"]
                    )
                )

            # -----------------------------------------
            # STEP 9: Determine final invoice status
            # -----------------------------------------

            has_failures = any(
                check["result"] == "fail"
                for check in all_checks
            )

            if has_failures:
                new_status = "discrepancy"
            else:
                new_status = "pending_approval"

            # -----------------------------------------
            # STEP 10: Update invoice status
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
                    new_status,
                    invoice_id
                )
            )

            # -----------------------------------------
            # STEP 11: Commit transaction
            # -----------------------------------------

            conn.commit()

            return {
                "message": (
                    "Invoice submitted successfully"
                    if new_status == "pending_approval"
                    else "Invoice has validation failures"
                ),
                "invoice_id": invoice_id,
                "status": new_status,
                "total_checks": len(all_checks),
                "failed_checks": sum(
                    1 for check in all_checks
                    if check["result"] == "fail"
                ),
                "warning_checks": sum(
                    1 for check in all_checks
                    if check["result"] == "warning"
                ),
                "checks": all_checks
            }

    except HTTPException:
        conn.rollback()
        raise

    except Exception as e:
        conn.rollback()

        print("Invoice submission error:", e)

        raise HTTPException(
            status_code=500,
            detail="Unable to submit invoice"
        )

    finally:
        conn.close()


