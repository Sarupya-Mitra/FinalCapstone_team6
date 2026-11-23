# from typing import Literal, Optional
# from datetime import date, datetime
# from decimal import Decimal
#
# from pydantic import BaseModel, ConfigDict
#
#
# AuditableInvoiceStatus = Literal[
#     "pending_approval",
#     "approved",
#     "rejected"
# ]
#
#
# class AuditorInvoiceResponse(BaseModel):
#
#     invoice_id: int
#     vendor_id: int
#     invoice_number: Optional[str] = None
#
#     invoice_date: Optional[date] = None
#     due_date: Optional[date] = None
#
#     currency: str
#     subtotal: Optional[Decimal] = None
#     tax_amount: Optional[Decimal] = None
#     total_amount: Optional[Decimal] = None
#
#     original_filename: str
#     file_size_bytes: int
#
#     status: AuditableInvoiceStatus
#     is_verified: bool
#
#     uploaded_by_clerk_id: int
#
#     created_at: datetime
#     updated_at: datetime
#
#     model_config = ConfigDict(from_attributes=True)
#
#
# class AuditorInvoiceListResponse(BaseModel):
#
#     total: int
#     limit: int
#     offset: int
#
#     invoices: list[AuditorInvoiceResponse]
#
# # =========================================================
# # AUDITOR INVOICE DETAILS
# # =========================================================
#
# class AuditorInvoiceDetails(BaseModel):
#
#     invoice_id: int
#     vendor_id: int
#     invoice_number: Optional[str] = None
#
#     invoice_date: Optional[date] = None
#     due_date: Optional[date] = None
#
#     currency: str
#     subtotal: Optional[Decimal] = None
#     tax_amount: Optional[Decimal] = None
#     total_amount: Optional[Decimal] = None
#
#     original_filename: str
#     file_size_bytes: int
#
#     status: Literal[
#         "pending_approval",
#         "approved",
#         "rejected"
#     ]
#
#     is_verified: bool
#     duplicate_of_invoice_id: Optional[int] = None
#     uploaded_by_clerk_id: int
#
#     created_at: datetime
#     updated_at: datetime
#
#     model_config = ConfigDict(from_attributes=True)
#
#
# # =========================================================
# # INVOICE LINE ITEMS
# # =========================================================
#
# class AuditorInvoiceItem(BaseModel):
#
#     item_id: int
#     invoice_id: int
#     line_no: int
#     item_name: str
#     quantity: Decimal
#     unit_price: Decimal
#     line_total: Optional[Decimal] = None
#     source: Literal["ai", "manual"]
#
#     model_config = ConfigDict(from_attributes=True)
#
#
# # =========================================================
# # INVOICE VALIDATION CHECKS
# # =========================================================
#
# class AuditorInvoiceCheck(BaseModel):
#
#     check_id: int
#     invoice_id: int
#     check_type: Literal[
#         "duplicate",
#         "line_total",
#         "invoice_total",
#         "missing_field",
#         "text_readable"
#     ]
#
#     result: Literal["pass", "fail", "warning"]
#     details: Optional[str] = None
#     checked_at: datetime
#
#     model_config = ConfigDict(from_attributes=True)
#
#
# # =========================================================
# # CLERK CORRECTION HISTORY
# # =========================================================
#
# class AuditorInvoiceCorrection(BaseModel):
#
#     correction_id: int
#     field_name: str
#     old_value: Optional[str] = None
#     new_value: Optional[str] = None
#     clerk_id: int
#     corrected_at: datetime
#
#     model_config = ConfigDict(from_attributes=True)
#
#
# # =========================================================
# # AI EXTRACTION HISTORY
# # =========================================================
#
# class AuditorExtractionHistory(BaseModel):
#
#     run_id: int
#     extracted_json: Optional[Any] = None
#     ai_summary: Optional[str] = None
#     provider: Optional[str] = None
#     model_name: Optional[str] = None
#
#     status: Literal[
#         "success",
#         "partial",
#         "failed",
#         "no_text",
#         "timeout",
#         "rate_limited"
#     ]
#
#     error_message: Optional[str] = None
#     duration_ms: Optional[int] = None
#     created_at: datetime
#
#     model_config = ConfigDict(from_attributes=True)
#
#
# # =========================================================
# # APPROVAL HISTORY
# # =========================================================
#
# class AuditorApprovalHistory(BaseModel):
#
#     approval_id: int
#     approver_id: int
#
#     decision: Literal["approved", "rejected"]
#     note: str
#     decided_at: datetime
#
#     model_config = ConfigDict(from_attributes=True)
#
#
# # =========================================================
# # COMPLETE AUDITOR INVOICE RESPONSE
# # =========================================================
#
# class AuditorInvoiceFullDetailsResponse(BaseModel):
#
#     invoice: AuditorInvoiceDetails
#
#     items: list[AuditorInvoiceItem]
#     checks: list[AuditorInvoiceCheck]
#     corrections: list[AuditorInvoiceCorrection]
#     extractions: list[AuditorExtractionHistory]
#     approvals: list[AuditorApprovalHistory]

# app/schemas/auditor.py

from typing import Optional, Literal, Any
from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


# =========================================================
# COMMON TYPES
# =========================================================

AuditableInvoiceStatus = Literal[
    "pending_approval",
    "approved",
    "rejected"
]

ApprovalDecision = Literal[
    "approved",
    "rejected"
]

ExtractionStatus = Literal[
    "success",
    "partial",
    "failed",
    "no_text",
    "timeout",
    "rate_limited"
]


# =========================================================
# AUDITOR INVOICE LIST
# =========================================================

class AuditorInvoiceResponse(BaseModel):

    invoice_id: int
    vendor_id: int
    invoice_number: Optional[str] = None

    invoice_date: Optional[date] = None
    due_date: Optional[date] = None

    currency: str
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None

    original_filename: str
    file_size_bytes: int

    status: AuditableInvoiceStatus
    is_verified: bool

    duplicate_of_invoice_id: Optional[int] = None
    uploaded_by_clerk_id: int

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditorInvoiceListResponse(BaseModel):

    total: int
    limit: int
    offset: int

    invoices: list[AuditorInvoiceResponse]


# =========================================================
# INVOICE DETAILS
# =========================================================

class AuditorInvoiceDetails(BaseModel):

    invoice_id: int
    vendor_id: int
    invoice_number: Optional[str] = None

    invoice_date: Optional[date] = None
    due_date: Optional[date] = None

    currency: str
    subtotal: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    total_amount: Optional[Decimal] = None

    original_filename: str
    file_size_bytes: int

    status: AuditableInvoiceStatus
    is_verified: bool

    duplicate_of_invoice_id: Optional[int] = None
    uploaded_by_clerk_id: int

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# INVOICE ITEMS
# =========================================================

class AuditorInvoiceItem(BaseModel):

    item_id: int
    invoice_id: int
    line_no: int
    item_name: str

    quantity: Decimal
    unit_price: Decimal
    line_total: Optional[Decimal] = None

    source: Literal["ai", "manual"]

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# VALIDATION CHECKS
# =========================================================

class AuditorInvoiceCheck(BaseModel):

    check_id: int
    invoice_id: int

    check_type: Literal[
        "duplicate",
        "line_total",
        "invoice_total",
        "missing_field",
        "text_readable"
    ]

    result: Literal["pass", "fail", "warning"]

    details: Optional[str] = None
    checked_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# CLERK CORRECTIONS
# =========================================================

class AuditorInvoiceCorrection(BaseModel):

    correction_id: int
    field_name: str

    old_value: Optional[str] = None
    new_value: Optional[str] = None

    clerk_id: int
    corrected_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# AI EXTRACTION HISTORY
# =========================================================

class AuditorExtractionHistory(BaseModel):

    run_id: int

    extracted_json: Optional[Any] = None
    ai_summary: Optional[str] = None

    provider: Optional[str] = None
    model_name: Optional[str] = None

    status: ExtractionStatus

    error_message: Optional[str] = None
    duration_ms: Optional[int] = None

    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# APPROVAL HISTORY
# =========================================================

class AuditorApprovalHistory(BaseModel):

    approval_id: int
    approver_id: int

    decision: ApprovalDecision
    note: str

    decided_at: datetime

    model_config = ConfigDict(from_attributes=True)


# =========================================================
# COMPLETE INVOICE DETAILS
# =========================================================

class AuditorInvoiceFullDetailsResponse(BaseModel):

    invoice: AuditorInvoiceDetails

    items: list[AuditorInvoiceItem]
    checks: list[AuditorInvoiceCheck]
    corrections: list[AuditorInvoiceCorrection]
    extractions: list[AuditorExtractionHistory]
    approvals: list[AuditorApprovalHistory]


# =========================================================
# REBUILD MODELS
# =========================================================

AuditorInvoiceFullDetailsResponse.model_rebuild()
AuditorInvoiceListResponse.model_rebuild()