from datetime import datetime, date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# -----------------------------------------
# Invoice check response
# -----------------------------------------

CheckResult = Literal["pass", "fail", "warning"]

CheckType = Literal[
    "duplicate",
    "line_total",
    "invoice_total",
    "missing_field",
    "text_readable"
]


class InvoiceCheckResponse(BaseModel):
    check_id: int
    invoice_id: int
    check_type: CheckType
    result: CheckResult
    details: str | None
    checked_at: datetime
    model_config = ConfigDict(from_attributes=True)


# -----------------------------------------
# Approver decision request
# -----------------------------------------

ApprovalDecision = Literal["approved", "rejected"]


class ApprovalDecisionSubmit(BaseModel):
    decision: ApprovalDecision
    note: str = Field(
        min_length=1,
        max_length=5000
    )


# -----------------------------------------
# Approval response
# -----------------------------------------

class ApprovalResponse(BaseModel):

    approval_id: int
    invoice_id: int
    approver_id: int
    decision: ApprovalDecision
    note: str
    decided_at: datetime
    model_config = ConfigDict(from_attributes=True)

