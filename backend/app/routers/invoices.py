from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile,File,Form
from typing import Optional
from pathlib import Path
import uuid
from pydantic import BaseModel, ConfigDict, Field, ValidationError
import fitz
import time,json

from app.schemas.invoice import InvoiceResponse,InvoiceSubmit,InvoiceExtractionResult
from app.db.database import get_connection_db
from app.routers.auth import require_role
from app.core.config import UPLOAD_DIR,MAX_FILE_SIZE,ALLOWED_EXTENSIONS,BASE_DIR

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
# getting a particular invoice by its invoice_id
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
                """,
                (invoice_id,)
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
    file_path = None
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

        # Generating an unique filename
        unique_filename = f"{uuid.uuid4()}.pdf"

        # Create upload directory if it doesn't exist
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        file_path = UPLOAD_DIR / unique_filename

        # Read and validate file contents
        file_size = 0
        with open(file_path,"wb") as destination:
            while True:
                chunk = file.file.read(1024*1024)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size>MAX_FILE_SIZE:
                    raise HTTPException(
                        status_code=413,
                        detail="File size exceeds the limit"
                    )
                if file_size <= 5 and not b"%PDF-".startswith(chunk[:file_size]):
                    raise HTTPException(
                        status_code=400,
                        detail="Invalid PDF file"
                    )
                destination.write(chunk)
        # Validate file is not empty
        if file_size == 0:
            raise HTTPException(
                status_code=400,
                detail = "Uploaded File is empty"
            )
        # Verify PDF signature
        with open(file_path, "rb") as uploaded_file:
            if uploaded_file.read(5) != b"%PDF-":
                raise HTTPException(
                    status_code=400,
                    detail="Invalid PDF file"
                )
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
                        file_path.relative_to(UPLOAD_DIR.parents[1]).as_posix(),
                        original_filename,
                        file_size,
                        clerk_id
                    )
                )
                row = cursor.fetchone()
                columns = [
                    description[0]
                    for description in cursor.description
                ]

                invoice = dict(zip(columns, row))

                conn.commit()

                return invoice
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    except Exception:
        # Delete saved file if anything goes wrong
        if file_path is not None and file_path.exists():
            file_path.unlink()
        raise
    finally:
        file.file.close()

###########################################################
# Extracting the pdf
###########################################################
def extract_text_from_pdf(file_path: Path) -> str:

    try:
        with fitz.open(file_path) as pdf:

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
            # STEP 3: Locate the stored PDF
            # ----------------------------------

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

            # ----------------------------------
            # STEP 4: Extract text using PyMuPDF
            # ----------------------------------

            extracted_text = extract_text_from_pdf(file_path)

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

            # TODO:
            # Pass extracted_text to your teammate's AI agent.
            #
            # The AI agent should:
            # 1. Read the extracted PDF text.
            # 2. Identify invoice information.
            # 3. Extract invoice line items.
            # 4. Return structured JSON.
            #
            # Expected output:
            #
            # ai_result = {
            #     "invoice_number": "INV-001",
            #     "invoice_date": "2026-11-15",
            #     "due_date": "2026-12-15",
            #     "currency": "USD",
            #     "subtotal": 1000.00,
            #     "tax_amount": 100.00,
            #     "total_amount": 1100.00,
            #     "items": [...]
            # }
            # TODO: Uncomment when AI agent is ready.

            # ai_result = your_ai_agent(extracted_text)

            sample_ai_result = {
                "invoice_number": "INV-2026-001",
                "invoice_date": "2026-11-15",
                "due_date": "2026-12-15",
                "currency": "USD",

                "subtotal": 1000.00,
                "tax_amount": 100.00,
                "total_amount": 1100.00,

                "items": [
                    {
                        "line_no": 1,
                        "item_name": "Dell Latitude 5450 Laptop",
                        "quantity": 2,
                        "unit_price": 400.00,
                        "line_total": 800.00
                    },
                    {
                        "line_no": 2,
                        "item_name": "Wireless Keyboard and Mouse Combo",
                        "quantity": 2,
                        "unit_price": 50.00,
                        "line_total": 100.00
                    },
                    {
                        "line_no": 3,
                        "item_name": "Laptop Carrying Bag",
                        "quantity": 2,
                        "unit_price": 50.00,
                        "line_total": 100.00
                    }
                ]
            }

            ## ----------------------------------
            ## STEP 6: VALIDATE AI OUTPUT
            ## ----------------------------------

            # validated_result = validate_ai_output(ai_result)
            validated_result = validate_ai_output(sample_ai_result)

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
                provider="your_provider",
                model_name="your_model",
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
