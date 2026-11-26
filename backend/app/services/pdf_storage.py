"""Compress uploaded invoice PDFs with PyMuPDF and store them in invoice_files.

Flow (called from POST /invoices):
    compressed = compress_pdf(raw_bytes)     # lossless first, lossy image passes only if needed
    upload_pdf(cursor, invoice_id, ...)      # INSERT into invoice_files (same transaction as the invoice)

Stored PDFs must be <= MAX_STORED_PDF_BYTES (1 MB) after compression.
"""
import hashlib
from urllib.parse import quote
from dataclasses import dataclass

import pymupdf as fitz  # PyMuPDF
from fastapi import HTTPException
from fastapi.responses import Response

from app.core.config import BASE_DIR, UPLOAD_DIR

MAX_STORED_PDF_BYTES = 1024 * 1024  # 1 MB, mirrors models.MAX_STORED_PDF_BYTES / ck_invoice_files_size

# Image-downsampling passes, tried in order only when lossless compression
# is not enough to get under 1 MB: (dpi_threshold, dpi_target, jpeg_quality).
# Images above dpi_threshold are resampled to dpi_target (PyMuPDF requires
# target < threshold). Kept at >= 96 dpi so scanned invoice text stays legible.
_LOSSY_PASSES = (
    (151, 150, 80),
    (121, 120, 65),
    (97, 96, 50),
)


@dataclass(frozen=True)
class CompressedPdf:
    data: bytes
    original_size: int
    page_count: int
    sha256: str  # of the original upload

    @property
    def stored_size(self) -> int:
        return len(self.data)


def _save_compressed(doc: fitz.Document) -> bytes:
    return doc.tobytes(
        garbage=4,           # drop unused/duplicate objects, compact xref
        deflate=True,        # compress uncompressed streams
        deflate_images=True,
        deflate_fonts=True,
        clean=True,          # sanitize content streams
        use_objstms=1,       # pack small objects into object streams
    )


def _open_pdf(raw: bytes) -> fitz.Document:
    try:
        doc = fitz.open(stream=raw, filetype="pdf")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid or corrupted PDF: {e}")
    if doc.needs_pass:
        doc.close()
        raise HTTPException(status_code=400, detail="Password-protected PDFs are not supported")
    if doc.page_count == 0:
        doc.close()
        raise HTTPException(status_code=400, detail="PDF has no pages")
    return doc


def compress_pdf(raw: bytes, max_bytes: int = MAX_STORED_PDF_BYTES) -> CompressedPdf:
    """Return the smallest PyMuPDF rewrite of `raw` that fits in `max_bytes`.

    Raises HTTP 400 for unreadable PDFs and HTTP 413 if even the most
    aggressive pass cannot get the file under the limit.
    """
    with _open_pdf(raw) as doc:
        page_count = doc.page_count
        best = _save_compressed(doc)

    # Never store something bigger than what was uploaded.
    if len(raw) < len(best):
        best = raw

    for dpi_threshold, dpi_target, quality in _LOSSY_PASSES:
        if len(best) <= max_bytes:
            break
        # Re-open from the original each time so passes don't compound artefacts.
        with _open_pdf(raw) as doc:
            doc.rewrite_images(dpi_threshold=dpi_threshold, dpi_target=dpi_target, quality=quality)
            candidate = _save_compressed(doc)
        if len(candidate) < len(best):
            best = candidate

    if len(best) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"PDF is {len(best) / 1024:.0f} KB after compression; "
                f"the limit is {max_bytes // 1024} KB. Please upload a smaller file."
            ),
        )

    return CompressedPdf(
        data=best,
        original_size=len(raw),
        page_count=page_count,
        sha256=hashlib.sha256(raw).hexdigest(),
    )


def upload_pdf(cursor, invoice_id: int, original_filename: str, pdf: CompressedPdf) -> dict:
    """Insert the compressed PDF for `invoice_id` into invoice_files.

    Uses the caller's cursor so it commits/rolls back together with the
    invoice row. Returns the stored file's metadata (without the bytes).
    """
    cursor.execute(
        """
        INSERT INTO invoice_files (
            invoice_id, file_data, original_filename, mime_type,
            original_size_bytes, stored_size_bytes, page_count, sha256
        )
        VALUES (%s, %s, %s, 'application/pdf', %s, %s, %s, %s)
        RETURNING file_id, invoice_id, original_size_bytes, stored_size_bytes, page_count, uploaded_at
        """,
        (
            invoice_id,
            pdf.data,  # psycopg2 adapts bytes -> BYTEA
            original_filename,
            pdf.original_size,
            pdf.stored_size,
            pdf.page_count,
            pdf.sha256,
        ),
    )
    columns = [d[0] for d in cursor.description]
    return dict(zip(columns, cursor.fetchone()))


def load_pdf(cursor, invoice_id: int) -> bytes | None:
    """Return the stored PDF bytes for an invoice, or None if it has none in the DB."""
    cursor.execute("SELECT file_data FROM invoice_files WHERE invoice_id = %s", (invoice_id,))
    row = cursor.fetchone()
    return bytes(row[0]) if row else None


def load_invoice_pdf_for_viewing(cursor, invoice_id: int) -> tuple[bytes, str] | None:
    """Return (pdf_bytes, filename) to show an invoice's PDF, or None if no file exists.

    Tries, in order: the untouched original upload on disk (invoice_original_files),
    the compressed copy in invoice_files, then a legacy on-disk invoices.file_path.
    """
    upload_root = UPLOAD_DIR.resolve()

    def _read_upload(relative_path: str) -> bytes | None:
        path = (BASE_DIR / relative_path).resolve()
        if not path.is_relative_to(upload_root) or not path.is_file():
            return None
        return path.read_bytes()

    cursor.execute(
        "SELECT original_filename, file_path FROM invoices WHERE invoice_id = %s",
        (invoice_id,),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    filename, legacy_path = row
    filename = filename or f"invoice-{invoice_id}.pdf"

    cursor.execute(
        "SELECT original_file_location FROM invoice_original_files WHERE invoice_id = %s",
        (invoice_id,),
    )
    original = cursor.fetchone()
    if original:
        data = _read_upload(original[0])
        if data is not None:
            return data, filename

    data = load_pdf(cursor, invoice_id)
    if data is not None:
        return data, filename

    if legacy_path and not legacy_path.startswith("db://"):
        data = _read_upload(legacy_path)
        if data is not None:
            return data, filename

    return None


def inline_pdf_response(pdf_bytes: bytes, filename: str):
    """FastAPI Response that displays the PDF in the browser instead of downloading it."""
    safe_ascii = "".join(c for c in filename if c.isascii() and c.isprintable() and c not in '"\\') or "invoice.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"inline; filename=\"{safe_ascii}\"; filename*=UTF-8''{quote(filename)}",
            "Cache-Control": "private, no-store",
        },
    )
