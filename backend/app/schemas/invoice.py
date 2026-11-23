
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict,Field


InvoiceStatus = Literal[
    "uploaded",
    "extracted",
    "pending_approval",
    "discrepancy",
    "approved",
    "rejected"
]


class InvoiceResponse(BaseModel):
    invoice_id: int
    vendor_id: int

    invoice_number: str | None
    invoice_date: date | None
    due_date: date | None

    currency: str
    subtotal: Decimal | None
    tax_amount: Decimal | None
    total_amount: Decimal | None

    original_filename: str
    file_size_bytes: int

    status: InvoiceStatus
    is_verified: bool
    duplicate_of_invoice_id: int | None

    uploaded_by_clerk_id: int

    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

class InvoiceItemSubmit(BaseModel):
    line_no: int = Field(ge=1)
    item_name: str = Field(min_length=1, max_length=300)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    line_total: Decimal | None = Field(default=None, ge=0)

class InvoiceSubmit(BaseModel):
    invoice_number: str | None = Field(
        default=None,
        max_length=100
    )

    invoice_date: date | None = None
    due_date: date | None = None

    currency: str = Field(
        min_length=3,
        max_length=3
    )

    subtotal: Decimal | None = Field(
        default=None,
        ge=0
    )

    tax_amount: Decimal | None = Field(
        default=None,
        ge=0
    )

    total_amount: Decimal | None = Field(
        default=None,
        ge=0
    )

    items: list[InvoiceItemSubmit] = Field(
        default_factory=list
    )

################################
# For the extraction of text from pdf
################################

class InvoiceExtractionResult(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None

    currency: str = Field(default="USD", min_length=3, max_length=3)

    subtotal: Decimal | None = Field(default=None, ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)
    total_amount: Decimal | None = Field(default=None, ge=0)

    items: list[InvoiceItemSubmit] = Field(default_factory=list)

### After uploading the pdf this is for fetching the extraction, for the clerk to validate and correct
class InvoiceItemResponse(BaseModel):
    item_id: int
    invoice_id: int
    line_no: int
    item_name: str
    quantity: Decimal
    unit_price: Decimal
    line_total: Decimal | None
    source: Literal["ai", "manual"]

    model_config = ConfigDict(from_attributes=True)


class InvoiceReviewResponse(BaseModel):
    invoice: InvoiceResponse
    items: list[InvoiceItemResponse]
    extraction: dict | None = None

#### For clerk correction or validation
class InvoiceItemCorrection(BaseModel):
    # Existing item: provide item_id
    # New item: leave item_id as None
    item_id: int | None = None

    line_no: int = Field(ge=1)
    item_name: str = Field(min_length=1, max_length=300)
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(ge=0)
    line_total: Decimal | None = Field(default=None, ge=0)


class InvoiceCorrectionSubmit(BaseModel):
    invoice_number: str | None = Field(
        default=None,
        max_length=100
    )

    invoice_date: date | None = None
    due_date: date | None = None

    currency: str = Field(
        min_length=3,
        max_length=3
    )

    subtotal: Decimal | None = Field(default=None, ge=0)
    tax_amount: Decimal | None = Field(default=None, ge=0)
    total_amount: Decimal | None = Field(default=None, ge=0)

    # Complete list of line items after clerk review
    items: list[InvoiceItemCorrection]