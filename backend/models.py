"""SQLAlchemy ORM models for the invoice_processing database.

Tables (per the project spec, section 03):
  clerks and approvers (user roles; login via app/routers/auth.py),
  auditors (read-only role, no APIs yet),
  vendors, invoices, invoice_items, invoice_checks, extraction_runs,
  invoice_approvals, invoice_files (compressed PDF bytes, <= 1 MB),
  plus invoice_corrections for the audit trail of
  clerk edits (original AI extraction is kept in extraction_runs).
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base

INVOICE_STATUSES = (
    "uploaded",          # PDF stored, not yet extracted
    "extracted",         # AI/manual fields present, unverified
    "pending_approval",  # clerk verified + submitted, checks passed
    "discrepancy",       # one or more checks failed, needs approver attention
    "approved",
    "rejected",
)


def _in(column: str, values) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class Clerk(Base):
    """Accounts-payable clerk: uploads invoices, verifies and corrects extracted data.

    Column names (c_*) match the queries in app/routers/auth.py.
    """

    __tablename__ = "clerks"

    c_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    c_name: Mapped[str] = mapped_column(String(100), nullable=False)
    c_email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    c_password: Mapped[str] = mapped_column(String(255), nullable=False)  # argon2 hash, never plain text
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="uploaded_by_clerk")
    corrections: Mapped[list["InvoiceCorrection"]] = relationship(back_populates="clerk")


class Approver(Base):
    """Reviewer who approves or rejects verified invoices.

    Column names (app_*) match the queries in app/routers/auth.py.
    """

    __tablename__ = "approvers"

    app_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    app_name: Mapped[str] = mapped_column(String(100), nullable=False)
    app_email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    app_password: Mapped[str] = mapped_column(String(255), nullable=False)  # argon2 hash, never plain text
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    approvals: Mapped[list["InvoiceApproval"]] = relationship(back_populates="approver")


class Auditor(Base):
    """Read-only reviewer: views processed invoices and traces the original
    extraction, clerk corrections and approver decisions (project spec, auditor flow).

    Column names (aud_*) follow the same pattern as clerks (c_*) and approvers (app_*).
    Not wired into app/routers/auth.py yet.
    """

    __tablename__ = "auditors"

    aud_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aud_name: Mapped[str] = mapped_column(String(100), nullable=False)
    aud_email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    aud_password: Mapped[str] = mapped_column(String(255), nullable=False)  # argon2 hash, never plain text
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Vendor(Base):
    __tablename__ = "vendors"

    vendor_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_name: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    contact_reference: Mapped[Optional[str]] = mapped_column(String(200))
    tax_id: Mapped[Optional[str]] = mapped_column(String(50))
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    invoices: Mapped[list["Invoice"]] = relationship(back_populates="vendor")


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint(_in("status", INVOICE_STATUSES), name="ck_invoices_status"),
        CheckConstraint("subtotal IS NULL OR subtotal >= 0", name="ck_invoices_subtotal"),
        CheckConstraint("tax_amount IS NULL OR tax_amount >= 0", name="ck_invoices_tax"),
        CheckConstraint("total_amount IS NULL OR total_amount >= 0", name="ck_invoices_total"),
        CheckConstraint("file_size_bytes > 0", name="ck_invoices_file_size"),
        # vendor + invoice number is unique among non-duplicate invoices.
        # A flagged duplicate is kept as its own row (pointing at the original
        # via duplicate_of_invoice_id) so the original is never overwritten.
        Index(
            "uq_invoices_vendor_number",
            "vendor_id",
            "invoice_number",
            unique=True,
            postgresql_where=text("duplicate_of_invoice_id IS NULL"),
        ),
        Index("ix_invoices_status", "status"),
    )

    invoice_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    vendor_id: Mapped[int] = mapped_column(
        ForeignKey("vendors.vendor_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    # Fields below hold the current (clerk-verified or extracted) values.
    # NULL = not yet known (e.g. unreadable PDF awaiting manual entry).
    invoice_number: Mapped[Optional[str]] = mapped_column(String(100))
    invoice_date: Mapped[Optional[date]] = mapped_column(Date)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default="USD")
    subtotal: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    tax_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    total_amount: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    # Source document reference, stored separately from extracted fields.
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="uploaded")
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    duplicate_of_invoice_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("invoices.invoice_id", ondelete="SET NULL")
    )
    uploaded_by_clerk_id: Mapped[int] = mapped_column(
        ForeignKey("clerks.c_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    vendor: Mapped[Vendor] = relationship(back_populates="invoices")
    uploaded_by_clerk: Mapped[Clerk] = relationship(back_populates="invoices")
    items: Mapped[list["InvoiceItem"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceItem.line_no"
    )
    checks: Mapped[list["InvoiceCheck"]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    extraction_runs: Mapped[list["ExtractionRun"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    approvals: Mapped[list["InvoiceApproval"]] = relationship(back_populates="invoice")
    corrections: Mapped[list["InvoiceCorrection"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    pdf_file: Mapped[Optional["InvoiceFile"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", uselist=False
    )


# Stored PDFs must be at most 1 MB after PyMuPDF compression.
MAX_STORED_PDF_BYTES = 1024 * 1024


class InvoiceFile(Base):
    """The uploaded invoice PDF itself, compressed with PyMuPDF and stored in the DB.

    One row per invoice. file_data holds the compressed bytes (<= 1 MB);
    original_size_bytes records what the clerk actually uploaded.
    """

    __tablename__ = "invoice_files"
    __table_args__ = (
        CheckConstraint(
            f"stored_size_bytes > 0 AND stored_size_bytes <= {MAX_STORED_PDF_BYTES}",
            name="ck_invoice_files_size",
        ),
        CheckConstraint("octet_length(file_data) = stored_size_bytes", name="ck_invoice_files_len"),
        CheckConstraint("original_size_bytes > 0", name="ck_invoice_files_orig_size"),
        CheckConstraint("mime_type = 'application/pdf'", name="ck_invoice_files_mime"),
    )

    file_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, unique=True
    )
    file_data: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)  # BYTEA
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False, server_default="application/pdf")
    original_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stored_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    page_count: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)  # hash of the original upload
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="pdf_file")


class InvoiceItem(Base):
    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_items_quantity"),
        CheckConstraint("unit_price >= 0", name="ck_items_unit_price"),
        CheckConstraint("source IN ('ai', 'manual')", name="ck_items_source"),
    )

    item_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True
    )
    line_no: Mapped[int] = mapped_column(Integer, nullable=False)
    item_name: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    # line_total as stated on the document; the app recomputes quantity * unit_price
    # deterministically and records any mismatch in invoice_checks.
    line_total: Mapped[Optional[Decimal]] = mapped_column(Numeric(14, 2))
    source: Mapped[str] = mapped_column(String(10), nullable=False, server_default="ai")

    invoice: Mapped[Invoice] = relationship(back_populates="items")


class InvoiceCheck(Base):
    __tablename__ = "invoice_checks"
    __table_args__ = (
        CheckConstraint(
            "check_type IN ('duplicate', 'line_total', 'invoice_total', 'missing_field', 'text_readable')",
            name="ck_checks_type",
        ),
        CheckConstraint("result IN ('pass', 'fail', 'warning')", name="ck_checks_result"),
    )

    check_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True
    )
    check_type: Mapped[str] = mapped_column(String(30), nullable=False)
    result: Mapped[str] = mapped_column(String(10), nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="checks")


class ExtractionRun(Base):
    """Immutable record of each AI (or failed) extraction attempt."""

    __tablename__ = "extraction_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('success', 'partial', 'failed', 'no_text', 'timeout', 'rate_limited')",
            name="ck_runs_status",
        ),
    )

    run_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True
    )
    extracted_json: Mapped[Optional[dict]] = mapped_column(JSONB)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    provider: Mapped[Optional[str]] = mapped_column(String(50))
    model_name: Mapped[Optional[str]] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="extraction_runs")


class InvoiceApproval(Base):
    """Append-only human decisions. Never updated by extraction runs."""

    __tablename__ = "invoice_approvals"
    __table_args__ = (
        CheckConstraint("decision IN ('approved', 'rejected')", name="ck_approvals_decision"),
        CheckConstraint("length(trim(note)) > 0", name="ck_approvals_note"),
    )

    approval_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.invoice_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    approver_id: Mapped[int] = mapped_column(
        ForeignKey("approvers.app_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    decision: Mapped[str] = mapped_column(String(10), nullable=False)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="approvals")
    approver: Mapped[Approver] = relationship(back_populates="approvals")


class InvoiceCorrection(Base):
    """Audit trail of clerk edits to extracted fields."""

    __tablename__ = "invoice_corrections"

    correction_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.invoice_id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_name: Mapped[str] = mapped_column(String(100), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    clerk_id: Mapped[int] = mapped_column(
        ForeignKey("clerks.c_id", ondelete="RESTRICT"), nullable=False, index=True
    )
    corrected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    invoice: Mapped[Invoice] = relationship(back_populates="corrections")
    clerk: Mapped[Clerk] = relationship(back_populates="corrections")
