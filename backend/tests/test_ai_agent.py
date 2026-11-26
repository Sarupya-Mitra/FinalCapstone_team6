"""Tests for backend/agent: output sanitising, redaction and the HTTP client.

The OpenRouter API is never called; chat_completion / urlopen are patched.
"""
import io
import json
import socket
import urllib.error

import pytest

from agent import agent as agent_module
from agent import client as client_module
from agent.agent import (
    _redact_sensitive,
    _sanitize_extraction,
    _to_iso_date,
    _to_number,
    review_invoice_with_ai,
    your_ai_agent,
)
from agent.client import AIAgentError, chat_completion, parse_json_response


# ---------------------------------------------------------------- helpers

@pytest.mark.parametrize(
    "value, expected",
    [
        (10, 10.0),
        ("1,234.50", 1234.5),
        ("$99.99", 99.99),
        ("0", 0.0),
        (None, None),
        (True, None),        # bools are not amounts
        ("", None),
        ("abc", None),
        (-5, None),          # negatives rejected
        ("NaN", None),
    ],
)
def test_to_number(value, expected):
    assert _to_number(value) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("2026-11-15", "2026-11-15"),
        (" 2026-01-02 ", "2026-01-02"),
        ("15/11/2026", None),
        ("2026-13-01", None),
        (20261115, None),
        (None, None),
    ],
)
def test_to_iso_date(value, expected):
    assert _to_iso_date(value) == expected


def test_redact_masks_iban_anywhere():
    text = "Pay to GB82WEST12345698765432 please"
    assert "GB82WEST12345698765432" not in _redact_sensitive(text)


def test_redact_masks_digits_on_bank_lines_only():
    text = "Account number: 1234 5678 9012\nInvoice INV-2024 total 1500"
    redacted = _redact_sensitive(text)
    assert "1234 5678 9012" not in redacted
    assert "Invoice INV-2024 total 1500" in redacted  # non-bank line untouched


# ---------------------------------------------------------------- _sanitize_extraction

def test_sanitize_extraction_normalises_fields():
    raw = {
        "invoice_number": "  INV-001 ",
        "invoice_date": "2026-11-15",
        "due_date": "not a date",
        "currency": "eur",
        "subtotal": "1,000.00",
        "tax_amount": 100,
        "total_amount": "1100",
        "items": [
            {"item_name": "Paper", "quantity": "2", "unit_price": "500", "line_total": "1000"},
        ],
    }

    result = _sanitize_extraction(raw)

    assert result == {
        "invoice_number": "INV-001",
        "invoice_date": "2026-11-15",
        "due_date": None,
        "currency": "EUR",
        "subtotal": 1000.0,
        "tax_amount": 100.0,
        "total_amount": 1100.0,
        "items": [
            {"line_no": 1, "item_name": "Paper", "quantity": 2.0, "unit_price": 500.0, "line_total": 1000.0}
        ],
    }


@pytest.mark.parametrize(
    "currency",
    [
        None,
        "US",
        "12$",
        pytest.param(
            "dollars",
            marks=pytest.mark.xfail(
                strict=True,
                reason="Known bug: agent.py truncates to 3 chars before validating, so 'dollars' -> 'DOL'",
            ),
        ),
    ],
)
def test_sanitize_extraction_falls_back_to_usd(currency):
    assert _sanitize_extraction({"currency": currency})["currency"] == "USD"


@pytest.mark.parametrize("placeholder", ["null", "None", "N/A", "not_found", "  "])
def test_sanitize_extraction_treats_placeholders_as_missing(placeholder):
    assert _sanitize_extraction({"invoice_number": placeholder})["invoice_number"] is None


def test_sanitize_extraction_drops_incomplete_items_and_renumbers():
    raw = {
        "items": [
            {"item_name": "", "quantity": 1, "unit_price": 1},          # no name
            {"item_name": "A", "quantity": 0, "unit_price": 1},         # zero qty
            {"item_name": "B", "quantity": 1, "unit_price": None},      # no price
            "not a dict",
            {"item_name": "Kept", "quantity": 3, "unit_price": 2},
        ]
    }
    items = _sanitize_extraction(raw)["items"]
    assert [(i["line_no"], i["item_name"]) for i in items] == [(1, "Kept")]


def test_sanitize_extraction_handles_non_list_items():
    assert _sanitize_extraction({"items": "oops"})["items"] == []


# ---------------------------------------------------------------- your_ai_agent

def test_your_ai_agent_sends_redacted_text_and_sanitises(monkeypatch):
    sent = {}

    def fake_chat(messages, **kwargs):
        sent["messages"] = messages
        return '```json\n{"invoice_number": "INV-9", "currency": "inr"}\n```'

    monkeypatch.setattr(agent_module, "chat_completion", fake_chat)

    result = your_ai_agent("Invoice INV-9\nIBAN: DE89370400440532013000")

    user_message = sent["messages"][1]["content"]
    assert "DE89370400440532013000" not in user_message
    assert result["invoice_number"] == "INV-9"
    assert result["currency"] == "INR"


def test_your_ai_agent_truncates_long_input(monkeypatch):
    sent = {}
    monkeypatch.setattr(agent_module.config, "AI_MAX_INPUT_CHARS", 50)
    monkeypatch.setattr(
        agent_module, "chat_completion", lambda m, **k: sent.setdefault("m", m) and "{}"
    )

    your_ai_agent("x" * 1000)

    assert sent["m"][1]["content"].count("x") == 50


def test_your_ai_agent_rejects_non_object_json(monkeypatch):
    monkeypatch.setattr(agent_module, "chat_completion", lambda m, **k: "[1, 2, 3]")
    with pytest.raises(AIAgentError):
        your_ai_agent("text")


# ---------------------------------------------------------------- review_invoice_with_ai

def test_review_downgrades_fail_and_filters_bad_checks(monkeypatch):
    response = {
        "checks": [
            {"check_type": "missing_field", "result": "fail", "details": "Due date missing"},
            {"check_type": "line_total", "result": "pass", "details": "OK"},
            {"check_type": "line_total", "result": "fail", "details": "dup type, dropped"},
            {"check_type": "made_up", "result": "pass", "details": "unknown type, dropped"},
            {"check_type": "duplicate", "result": "maybe", "details": "bad result, dropped"},
            {"check_type": "invoice_total", "result": "pass", "details": ""},  # no details
            "garbage",
        ]
    }
    monkeypatch.setattr(agent_module, "chat_completion", lambda m, **k: json.dumps(response))

    checks = review_invoice_with_ai({"invoice_number": "INV-1"}, [])

    assert checks == [
        {"check_type": "missing_field", "result": "warning", "details": "[AI advisory] Due date missing"},
        {"check_type": "line_total", "result": "pass", "details": "[AI advisory] OK"},
    ]


def test_review_raises_when_checks_missing(monkeypatch):
    monkeypatch.setattr(agent_module, "chat_completion", lambda m, **k: '{"result": "ok"}')
    with pytest.raises(AIAgentError):
        review_invoice_with_ai({}, [])


def test_review_only_sends_whitelisted_fields(monkeypatch):
    sent = {}
    monkeypatch.setattr(
        agent_module,
        "chat_completion",
        lambda m, **k: sent.setdefault("m", m) and '{"checks": []}',
    )

    review_invoice_with_ai(
        {"invoice_number": "INV-1", "uploaded_by_clerk_id": 3, "file_path": "secret/path.pdf"},
        [{"line_no": 1, "item_name": "Pen", "quantity": 1, "unit_price": 1, "line_total": 1, "item_id": 77}],
    )

    payload = json.loads(sent["m"][1]["content"])
    assert "file_path" not in payload["invoice"]
    assert "uploaded_by_clerk_id" not in payload["invoice"]
    assert "item_id" not in payload["items"][0]


# ---------------------------------------------------------------- parse_json_response

@pytest.mark.parametrize(
    "content",
    [
        '{"a": 1}',
        '```json\n{"a": 1}\n```',
        '```\n{"a": 1}\n```',
        'Sure! Here is the JSON: {"a": 1} Hope that helps.',
    ],
)
def test_parse_json_response_tolerates_fences_and_prose(content):
    assert parse_json_response(content) == {"a": 1}


def test_parse_json_response_raises_on_invalid_json():
    with pytest.raises(AIAgentError):
        parse_json_response("no json here")


# ---------------------------------------------------------------- chat_completion

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setattr(client_module.config, "OPENROUTER_API_KEY", "test-key")


def _patch_urlopen(monkeypatch, result):
    def fake_urlopen(request, timeout):
        if isinstance(result, BaseException):
            raise result
        return _FakeResponse(json.dumps(result).encode())

    monkeypatch.setattr(client_module.urllib.request, "urlopen", fake_urlopen)


def test_chat_completion_requires_api_key(monkeypatch):
    monkeypatch.setattr(client_module.config, "OPENROUTER_API_KEY", "")
    with pytest.raises(AIAgentError, match="not configured"):
        chat_completion([])


def test_chat_completion_returns_message_content(monkeypatch, api_key):
    _patch_urlopen(monkeypatch, {"choices": [{"message": {"content": "hello"}}]})
    assert chat_completion([{"role": "user", "content": "hi"}]) == "hello"


@pytest.mark.parametrize(
    "code, run_status",
    [(429, "rate_limited"), (401, "failed"), (402, "failed"), (504, "timeout"), (500, "failed")],
)
def test_chat_completion_maps_http_errors(monkeypatch, api_key, code, run_status):
    error = urllib.error.HTTPError("url", code, "msg", {}, None)
    _patch_urlopen(monkeypatch, error)

    with pytest.raises(AIAgentError) as exc:
        chat_completion([])
    assert exc.value.run_status == run_status
    assert "test-key" not in str(exc.value)  # never leak the API key


def test_chat_completion_maps_socket_timeout(monkeypatch, api_key):
    _patch_urlopen(monkeypatch, socket.timeout())
    with pytest.raises(AIAgentError) as exc:
        chat_completion([])
    assert exc.value.run_status == "timeout"


def test_chat_completion_maps_unreachable_host(monkeypatch, api_key):
    _patch_urlopen(monkeypatch, urllib.error.URLError("no route"))
    with pytest.raises(AIAgentError, match="unreachable"):
        chat_completion([])


def test_chat_completion_handles_error_inside_200(monkeypatch, api_key):
    _patch_urlopen(monkeypatch, {"error": {"code": 429, "message": "slow down"}})
    with pytest.raises(AIAgentError) as exc:
        chat_completion([])
    assert exc.value.run_status == "rate_limited"


@pytest.mark.parametrize("body", [{"choices": []}, {"choices": [{"message": {"content": "  "}}]}])
def test_chat_completion_rejects_empty_completion(monkeypatch, api_key, body):
    _patch_urlopen(monkeypatch, body)
    with pytest.raises(AIAgentError):
        chat_completion([])
