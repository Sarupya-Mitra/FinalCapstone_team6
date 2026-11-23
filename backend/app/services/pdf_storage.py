"""Compress uploaded invoice PDFs with PyMuPDF and store them in invoice_files.

Flow (called from POST /invoices):
    compressed = compress_pdf(raw_bytes)     # lossless first, lossy image passes only if needed
    upload_pdf(cursor, invoice_id, ...)      # INSERT into invoice_files (same transaction as the invoice)

Stored PDFs must be <= MAX_STORED_PDF_BYTES (1 MB) after compression.
"""
import hashlib
from dataclasses import dataclass

import pymupdf as fitz  # PyMuPDF
from fastapi import HTTPException

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
