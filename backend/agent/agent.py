"""
Invoice AI agent (OpenRouter).

- your_ai_agent(extracted_text): proposes invoice fields from PDF text.
- review_invoice_with_ai(invoice, items): advisory checks before submission.

Model output is sanitised here so it always matches the shapes expected by
app/routers/invoices.py. Arithmetic and duplicate detection stay in Python.
"""
import json
import re
from datetime import date
from decimal import Decimal, InvalidOperation

from agent import config
from agent.client import AIAgentError, chat_completion, parse_json_response
from agent.prompts import CHECKS_SYSTEM_PROMPT, EXTRACTION_SYSTEM_PROMPT

ALLOWED_CHECK_TYPES = {
    "duplicate", "line_total", "invoice_total", "missing_field", "text_readable"
}
ALLOWED_CHECK_RESULTS = {"pass", "warning", "fail"}

# Banking data must not be sent to the external model
_BANK_LINE = re.compile(
    r"\b(iban|swift|bic|acct|account\s*(no|number|#)|routing|sort\s*code|bank)\b",
    re.IGNORECASE,
)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_DIGIT_RUN = re.compile(r"\d[\d \-]{3,}\d")


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
def _redact_sensitive(text: str) -> str:
    lines = []
    for line in text.splitlines():
        line = _IBAN.sub("[REDACTED]", line)
        if _BANK_LINE.search(line):
            line = _DIGIT_RUN.sub("[REDACTED]", line)
        lines.append(line)
    return "\n".join(lines)


def _to_number(value) -> float | None:
    """Non-negative finite number or None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str):
        value = re.sub(r"[^\d.\-]", "", value)
        if not value:
            return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return float(number)


def _to_iso_date(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return date.fromisoformat(value.strip()).isoformat()
    except ValueError:
        return None


def _to_text(value, max_length: int) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "not_found", "n/a"}:
        return None
    return text[:max_length]


def _sanitize_extraction(raw: dict) -> dict:
    currency = _to_text(raw.get("currency"), 3)
    currency = (
        currency.upper()
        if currency and len(currency) == 3 and currency.isalpha()
        else "USD"
    )

    items = []
    raw_items = raw.get("items")
    for raw_item in raw_items if isinstance(raw_items, list) else []:
        if not isinstance(raw_item, dict):
            continue
        item_name = _to_text(raw_item.get("item_name"), 300)
        quantity = _to_number(raw_item.get("quantity"))
        unit_price = _to_number(raw_item.get("unit_price"))
        # Skip items without explicit name / quantity / price
        if not item_name or not quantity or unit_price is None:
            continue
        items.append({
            "line_no": len(items) + 1,
            "item_name": item_name,
            "quantity": quantity,
            "unit_price": unit_price,
            "line_total": _to_number(raw_item.get("line_total")),
        })

    return {
        "invoice_number": _to_text(raw.get("invoice_number"), 100),
        "invoice_date": _to_iso_date(raw.get("invoice_date")),
        "due_date": _to_iso_date(raw.get("due_date")),
        "currency": currency,
        "subtotal": _to_number(raw.get("subtotal")),
        "tax_amount": _to_number(raw.get("tax_amount")),
        "total_amount": _to_number(raw.get("total_amount")),
        "items": items,
    }


# ------------------------------------------------------------------
# Stage 1: field extraction
# ------------------------------------------------------------------
def your_ai_agent(extracted_text: str) -> dict:
    """
    Propose structured invoice fields from PDF text.

    Returns:
        {
            "invoice_number": "INV-001",
            "invoice_date": "2026-11-15",
            "due_date": "2026-12-15",
            "currency": "USD",
            "subtotal": 1000.00,
            "tax_amount": 100.00,
            "total_amount": 1100.00,
            "items": [{"line_no", "item_name", "quantity",
                       "unit_price", "line_total"}, ...]
        }

    Raises:
        AIAgentError: model unreachable / timed out / rate limited / bad output.
    """
    text = _redact_sensitive(extracted_text)[: config.AI_MAX_INPUT_CHARS]

    content = chat_completion([
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"<<<INVOICE_TEXT>>>\n{text}\n<<<END_INVOICE_TEXT>>>",
        },
    ])

    raw = parse_json_response(content)
    if not isinstance(raw, dict):
        raise AIAgentError("AI response was not a JSON object")

    return _sanitize_extraction(raw)


# ------------------------------------------------------------------
# Stage 2: advisory review before submission
# ------------------------------------------------------------------
def review_invoice_with_ai(invoice: dict, items: list[dict]) -> list[dict]:
    """
    Advisory AI checks on a clerk-reviewed invoice.

    Returns:
        [{"check_type": "missing_field", "result": "pass", "details": "..."}, ...]

    AI findings are advisory, so a model "fail" is stored as "warning";
    only deterministic Python checks can fail an invoice.

    Raises:
        AIAgentError: model unreachable / timed out / rate limited / bad output.
    """
    header_fields = (
        "invoice_number", "invoice_date", "due_date", "currency",
        "subtotal", "tax_amount", "total_amount",
    )
    item_fields = ("line_no", "item_name", "quantity", "unit_price", "line_total")

    payload = {
        "invoice": {field: invoice.get(field) for field in header_fields},
        "items": [
            {field: item.get(field) for field in item_fields}
            for item in items
        ],
    }

    content = chat_completion(
        [
            {"role": "system", "content": CHECKS_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, default=str)},
        ],
        max_tokens=1000,
    )

    raw = parse_json_response(content)
    raw_checks = raw.get("checks") if isinstance(raw, dict) else None
    if not isinstance(raw_checks, list):
        raise AIAgentError("AI response did not contain a checks list")

    checks = []
    seen_types = set()
    for check in raw_checks:
        if not isinstance(check, dict):
            continue
        check_type = str(check.get("check_type", "")).strip().lower()
        result = str(check.get("result", "")).strip().lower()
        details = _to_text(check.get("details"), 300)

        if (
            check_type not in ALLOWED_CHECK_TYPES
            or result not in ALLOWED_CHECK_RESULTS
            or check_type in seen_types
            or not details
        ):
            continue
        seen_types.add(check_type)

        checks.append({
            "check_type": check_type,
            "result": "warning" if result == "fail" else result,
            "details": f"[AI advisory] {details}",
        })

    return checks
