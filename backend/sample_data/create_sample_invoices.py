"""Generate short, TEXT-BASED fictional invoice PDFs for testing.

Produces two sets of files in sample_data/pdfs/:

* The six fixed test-case PDFs (01_..06_), always regenerated so tests stay stable.
* N random invoices (rand_###_<scenario>.pdf) covering these scenarios:
    - valid               : arithmetic and fields are all correct
    - missing_field       : invoice number, date, subtotal, tax, total, currency
                            or all line items are left off the document
    - arithmetic_mismatch : a line total, the subtotal or the grand total is wrong
    - duplicate_id        : re-uses the vendor + invoice number of an earlier invoice
    - invalid_date        : impossible / malformed date, due date before invoice
                            date, or a date in the future
  each rendered with one of several layouts (classic, table, modern, receipt).

A manifest.json describing every generated file (scenario, what was broken,
layout and the expected correct values) is written next to the PDFs.

Run:
    python sample_data/create_sample_invoices.py                 # 20 random + fixed
    python sample_data/create_sample_invoices.py --count 50 --seed 7
    python sample_data/create_sample_invoices.py --scenarios valid invalid_date
    python sample_data/create_sample_invoices.py --no-fixed

All vendors and data are fictional. No scanned images or real banking information.
"""

import argparse
import json
import random
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # older PyMuPDF releases only ship the `fitz` name
    import fitz

OUTPUT_DIR = Path(__file__).parent / "pdfs"
TODAY = date(2026, 11, 26)

# --------------------------------------------------------------------------- #
# Fixed examples (the required test cases)
# --------------------------------------------------------------------------- #
EXAMPLES = {
    "01_valid_abc.pdf": [
        "ABC Technologies", "Invoice Number: ABC-101", "Invoice Date: 2026-11-19",
        "Keyboard | Qty: 2 | Unit Price: 1000.00 | Line Total: 2000.00",
        "Mouse | Qty: 3 | Unit Price: 500.00 | Line Total: 1500.00",
        "Subtotal: 3500.00", "Tax: 0.00", "Total: 3500.00", "Currency: INR",
    ],
    "02_arithmetic_mismatch_abc.pdf": [
        "ABC Technologies", "Invoice Number: ABC-102", "Invoice Date: 2026-11-19",
        "Keyboard | Qty: 2 | Unit Price: 1000.00 | Line Total: 2000.00",
        "Mouse | Qty: 3 | Unit Price: 500.00 | Line Total: 1500.00",
        "Subtotal: 3500.00", "Tax: 0.00", "Total: 4000.00", "Currency: INR",
    ],
    "03_duplicate_number_abc.pdf": [
        "ABC Technologies", "Invoice Number: ABC-101", "Invoice Date: 2026-11-20",
        "Monitor | Qty: 1 | Unit Price: 5000.00 | Line Total: 5000.00",
        "Subtotal: 5000.00", "Tax: 0.00", "Total: 5000.00", "Currency: INR",
    ],
    "04_missing_tax_bright.pdf": [
        "Bright Office Supplies", "Invoice Number: BRI-301", "Invoice Date: 2026-11-18",
        "Paper Ream | Qty: 5 | Unit Price: 250.00 | Line Total: 1250.00",
        "Subtotal: 1250.00", "Total: 1250.00", "Currency: INR",
    ],
    "05_missing_total_bright.pdf": [
        "Bright Office Supplies", "Invoice Number: BRI-302", "Invoice Date: 2026-11-19",
        "Printer Ink | Qty: 2 | Unit Price: 900.00 | Line Total: 1800.00",
        "Subtotal: 1800.00", "Tax: 0.00", "Currency: INR",
    ],
    "06_valid_metro.pdf": [
        "Metro Logistics", "Invoice Number: MET-500", "Invoice Date: 2026-11-19",
        "Delivery | Qty: 4 | Unit Price: 600.00 | Line Total: 2400.00",
        "Subtotal: 2400.00", "Tax: 432.00", "Total: 2832.00", "Currency: INR",
    ],
}

# Invoice numbers already used by the fixed examples (candidates for duplicates).
FIXED_NUMBERS = [
    ("ABC Technologies", "ABC-101"), ("ABC Technologies", "ABC-102"),
    ("Bright Office Supplies", "BRI-301"), ("Bright Office Supplies", "BRI-302"),
    ("Metro Logistics", "MET-500"),
]

# --------------------------------------------------------------------------- #
# Random data pools (all fictional)
# --------------------------------------------------------------------------- #
VENDORS = [
    {"name": "ABC Technologies", "prefix": "ABC", "city": "Bengaluru", "tax_id": "ABC-TX-0101",
     "items": [("Keyboard", 800, 2500), ("Mouse", 300, 1200), ("Monitor", 7000, 18000),
               ("USB-C Hub", 900, 3000), ("Laptop Stand", 600, 2200)]},
    {"name": "Bright Office Supplies", "prefix": "BRI", "city": "Pune", "tax_id": "BRI-TX-0301",
     "items": [("Paper Ream", 200, 350), ("Printer Ink", 700, 1500), ("Stapler", 120, 400),
               ("File Folder Pack", 150, 450), ("Whiteboard Markers", 90, 300)]},
    {"name": "Metro Logistics", "prefix": "MET", "city": "Mumbai", "tax_id": "MET-TX-0500",
     "items": [("Delivery", 400, 900), ("Express Courier", 600, 1500), ("Warehousing (per day)", 1500, 4000),
               ("Packaging", 100, 500)]},
    {"name": "Acme Office Supplies", "prefix": "INV", "city": "Chennai", "tax_id": "ACME-TX-1001",
     "items": [("Desk Organizer", 250, 900), ("Ergonomic Chair", 6000, 15000), ("Notebook Pack", 150, 500)]},
    {"name": "Nimbus Cloud Services", "prefix": "NCS", "city": "Hyderabad", "tax_id": "NCS-TX-2002",
     "items": [("Cloud Compute (hours)", 8, 40), ("Object Storage (GB)", 2, 6), ("Support Plan", 5000, 12000),
               ("Managed Database", 3000, 9000)]},
    {"name": "BlueRiver Logistics", "prefix": "BRL", "city": "Kolkata", "tax_id": "BRL-TX-3003",
     "items": [("Freight Charges", 2000, 8000), ("Loading Labour", 500, 1500), ("Fuel Surcharge", 300, 1200)]},
    {"name": "Greenleaf Catering", "prefix": "GLC", "city": "Delhi", "tax_id": "GLC-TX-4004",
     "items": [("Lunch Buffet (per plate)", 250, 600), ("Tea/Coffee Service", 40, 120), ("Event Setup", 2000, 6000)]},
]

TAX_RATES = [Decimal("0"), Decimal("5"), Decimal("12"), Decimal("18")]
CURRENCIES = ["INR"] * 6 + ["USD", "EUR"]
SCENARIOS = ["valid", "missing_field", "arithmetic_mismatch", "duplicate_id", "invalid_date"]
LAYOUTS = ["classic", "table", "modern", "receipt"]
MISSING_FIELDS = ["invoice_number", "invoice_date", "subtotal", "tax", "total", "currency", "items"]

CENT = Decimal("0.01")


def money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def fmt_money(value):
    return f"{value:.2f}"


# --------------------------------------------------------------------------- #
# Invoice data generation
# --------------------------------------------------------------------------- #
def build_valid_invoice(rng, vendor, number):
    n_items = rng.randint(1, 5)
    picks = rng.sample(vendor["items"], k=min(n_items, len(vendor["items"])))
    items = []
    for name, lo, hi in picks:
        qty = rng.randint(1, 12)
        price = money(rng.randint(lo * 100, hi * 100) / 100)
        items.append({"name": name, "qty": qty, "unit_price": price, "line_total": money(price * qty)})
    subtotal = money(sum(i["line_total"] for i in items))
    rate = rng.choice(TAX_RATES)
    tax = money(subtotal * rate / 100)
    inv_date = TODAY - timedelta(days=rng.randint(1, 120))
    return {
        "vendor": vendor,
        "invoice_number": number,
        "invoice_date": inv_date,
        "due_date": inv_date + timedelta(days=rng.choice([15, 30, 45, 60])),
        "currency": rng.choice(CURRENCIES),
        "items": items,
        "subtotal": subtotal,
        "tax_rate": rate,
        "tax": tax,
        "total": subtotal + tax,
        # Raw display overrides for dates (used by the invalid_date scenario).
        "invoice_date_text": None,
        "due_date_text": None,
    }


def expected_values(inv):
    """Snapshot of the correct values before any defect is introduced."""
    return {
        "vendor": inv["vendor"]["name"],
        "invoice_number": inv["invoice_number"],
        "invoice_date": inv["invoice_date"].isoformat(),
        "due_date": inv["due_date"].isoformat(),
        "currency": inv["currency"],
        "subtotal": fmt_money(inv["subtotal"]),
        "tax": fmt_money(inv["tax"]),
        "total": fmt_money(inv["total"]),
        "items": [
            {"item_name": i["name"], "quantity": i["qty"], "unit_price": fmt_money(i["unit_price"]),
             "line_total": fmt_money(i["line_total"])}
            for i in inv["items"]
        ],
    }


def nudge(rng, value):
    """Return a plausibly wrong amount that differs from `value`."""
    delta = money(rng.choice([1, 5, 10, 50, 100, 250, 500]) * rng.choice([1, -1]))
    wrong = value + delta
    return wrong if wrong > 0 else value + abs(delta)


def apply_missing_field(rng, inv):
    field = rng.choice(MISSING_FIELDS)
    if field == "items":
        inv["items"] = []
    else:
        inv[field] = None
    return f"missing {field}"


def apply_arithmetic_mismatch(rng, inv):
    kind = rng.choice(["line_total", "subtotal", "total"])
    if kind == "line_total":
        item = rng.choice(inv["items"])
        correct = item["line_total"]
        item["line_total"] = nudge(rng, correct)
        return (f"line total for '{item['name']}' is {fmt_money(item['line_total'])}, "
                f"expected {item['qty']} x {fmt_money(item['unit_price'])} = {fmt_money(correct)}")
    if kind == "subtotal":
        correct = inv["subtotal"]
        inv["subtotal"] = nudge(rng, correct)
        return f"subtotal is {fmt_money(inv['subtotal'])}, sum of line totals is {fmt_money(correct)}"
    correct = inv["total"]
    inv["total"] = nudge(rng, correct)
    return f"total is {fmt_money(inv['total'])}, subtotal + tax is {fmt_money(correct)}"


def apply_invalid_date(rng, inv):
    kind = rng.choice(["impossible_day", "invalid_month", "malformed", "due_before_invoice", "future_date"])
    year = inv["invoice_date"].year
    if kind == "impossible_day":
        bad = rng.choice([f"{year}-02-30", f"{year}-04-31", f"{year}-06-31", f"{year}-11-31", f"{year}-02-29"])
        inv["invoice_date_text"] = bad
        return f"invoice date {bad} does not exist"
    if kind == "invalid_month":
        bad = f"{year}-{rng.choice([13, 14, 0]):02d}-{rng.randint(1, 28):02d}"
        inv["invoice_date_text"] = bad
        return f"invoice date {bad} has an invalid month"
    if kind == "malformed":
        bad = rng.choice(["32/11/2026", "2026/19/11", "N0v 1g 2026", "19-11-20266", "TBD", "00-00-0000"])
        inv["invoice_date_text"] = bad
        return f"invoice date '{bad}' is malformed"
    if kind == "due_before_invoice":
        inv["due_date"] = inv["invoice_date"] - timedelta(days=rng.randint(5, 40))
        return f"due date {inv['due_date']} is before invoice date {inv['invoice_date']}"
    inv["invoice_date"] = TODAY + timedelta(days=rng.randint(30, 400))
    inv["due_date"] = inv["invoice_date"] + timedelta(days=30)
    return f"invoice date {inv['invoice_date']} is in the future"


# --------------------------------------------------------------------------- #
# Layout rendering
# --------------------------------------------------------------------------- #
DATE_STYLES = {
    "classic": "%Y-%m-%d",
    "table": "%d %b %Y",
    "modern": "%B %d, %Y",
    "receipt": "%d-%b-%Y",
}


def date_text(inv, field, layout):
    raw = inv.get(f"{field}_text")
    if raw:
        return raw
    value = inv[field]
    return value.strftime(DATE_STYLES[layout]) if value else None


def text(page, x, y, s, size=10, font="helv", color=(0, 0, 0)):
    page.insert_text((x, y), s, fontsize=size, fontname=font, color=color)


def rtext(page, right_x, y, s, size=10, font="helv", color=(0, 0, 0)):
    width = fitz.get_text_length(s, fontname=font, fontsize=size)
    text(page, right_x - width, y, s, size, font, color)


def tax_label(inv, word="Tax"):
    return f"{word} ({inv['tax_rate']}%)" if inv["tax_rate"] else word


def render_classic(page, inv):
    """Plain 'Label: value' lines, same style as the fixed examples."""
    v = inv["vendor"]
    lines = [v["name"]]
    if inv["invoice_number"]:
        lines.append(f"Invoice Number: {inv['invoice_number']}")
    if d := date_text(inv, "invoice_date", "classic"):
        lines.append(f"Invoice Date: {d}")
    if d := date_text(inv, "due_date", "classic"):
        lines.append(f"Due Date: {d}")
    for it in inv["items"]:
        lines.append(f"{it['name']} | Qty: {it['qty']} | Unit Price: {fmt_money(it['unit_price'])} "
                     f"| Line Total: {fmt_money(it['line_total'])}")
    if inv["subtotal"] is not None:
        lines.append(f"Subtotal: {fmt_money(inv['subtotal'])}")
    if inv["tax"] is not None:
        lines.append(f"{tax_label(inv)}: {fmt_money(inv['tax'])}")
    if inv["total"] is not None:
        lines.append(f"Total: {fmt_money(inv['total'])}")
    if inv["currency"]:
        lines.append(f"Currency: {inv['currency']}")
    y = 80
    for line in lines:
        text(page, 72, y, line)
        y += 24


def render_table(page, inv):
    """Formal invoice: vendor top-left, meta top-right, gridded item table."""
    v = inv["vendor"]
    right = 540
    text(page, 50, 70, v["name"], 16, "hebo")
    text(page, 50, 88, f"{v['city']}, India")
    text(page, 50, 102, f"Tax ID: {v['tax_id']}")
    rtext(page, right, 70, "INVOICE", 22, "hebo", (0.2, 0.2, 0.5))

    y = 100
    meta = [("Invoice #", inv["invoice_number"]),
            ("Date", date_text(inv, "invoice_date", "table")),
            ("Due", date_text(inv, "due_date", "table")),
            ("Currency", inv["currency"])]
    for label, val in meta:
        if val:
            text(page, 370, y, f"{label}:", 10, "hebo")
            rtext(page, right, y, val)
            y += 15

    text(page, 50, 150, "Bill To:", 10, "hebo")
    text(page, 50, 164, "Team6 Finance Dept., Accounts Payable")

    cols = [50, 300, 360, 450, right]
    top = 190
    row_h = 20
    page.draw_rect(fitz.Rect(cols[0], top, right, top + row_h), color=(0, 0, 0), fill=(0.9, 0.9, 0.95))
    headers = ["Description", "Qty", "Rate", "Amount"]
    for i, h in enumerate(headers):
        if i == 0:
            text(page, cols[i] + 5, top + 14, h, 10, "hebo")
        else:
            rtext(page, cols[i + 1] - 5, top + 14, h, 10, "hebo")
    y = top + row_h
    for it in inv["items"]:
        page.draw_rect(fitz.Rect(cols[0], y, right, y + row_h), color=(0, 0, 0))
        text(page, cols[0] + 5, y + 14, it["name"])
        rtext(page, cols[2] - 5, y + 14, str(it["qty"]))
        rtext(page, cols[3] - 5, y + 14, fmt_money(it["unit_price"]))
        rtext(page, cols[4] - 5, y + 14, fmt_money(it["line_total"]))
        y += row_h
    for x in cols[1:-1]:
        page.draw_line(fitz.Point(x, top), fitz.Point(x, y), color=(0, 0, 0))

    y += 25
    for label, val, bold in [("Subtotal", inv["subtotal"], False),
                             (tax_label(inv, "GST"), inv["tax"], False),
                             ("Total Due", inv["total"], True)]:
        if val is not None:
            font = "hebo" if bold else "helv"
            text(page, 380, y, label, 10, font)
            rtext(page, right - 5, y, fmt_money(val), 10, font)
            y += 16
    text(page, 50, 760, "Thank you for your business.", 9, "helv", (0.4, 0.4, 0.4))


def render_modern(page, inv):
    """Coloured header band, different labels (Bill No., Dated, Grand Total)."""
    v = inv["vendor"]
    accent = (0.05, 0.45, 0.45)
    page.draw_rect(fitz.Rect(0, 0, page.rect.width, 90), color=None, fill=accent)
    text(page, 40, 45, v["name"].upper(), 18, "hebo", (1, 1, 1))
    text(page, 40, 68, f"{v['city']}  |  GSTIN {v['tax_id']}", 9, "helv", (1, 1, 1))
    rtext(page, 555, 55, "TAX INVOICE", 14, "hebo", (1, 1, 1))

    y = 125
    pairs = [("Bill No.", inv["invoice_number"]),
             ("Dated", date_text(inv, "invoice_date", "modern")),
             ("Payment Due", date_text(inv, "due_date", "modern")),
             ("Amounts in", inv["currency"])]
    for i, (label, val) in enumerate(pairs):
        if not val:
            continue
        x = 40 if i % 2 == 0 else 310
        text(page, x, y + (i // 2) * 30, label, 8, "helv", (0.4, 0.4, 0.4))
        text(page, x, y + (i // 2) * 30 + 13, val, 11, "hebo")

    y = 210
    text(page, 40, y, "#", 9, "hebo", accent)
    text(page, 60, y, "ITEM", 9, "hebo", accent)
    rtext(page, 360, y, "QTY", 9, "hebo", accent)
    rtext(page, 450, y, "PRICE", 9, "hebo", accent)
    rtext(page, 555, y, "AMOUNT", 9, "hebo", accent)
    page.draw_line(fitz.Point(40, y + 6), fitz.Point(555, y + 6), color=accent, width=1.5)
    y += 24
    for n, it in enumerate(inv["items"], start=1):
        text(page, 40, y, str(n))
        text(page, 60, y, it["name"])
        rtext(page, 360, y, str(it["qty"]))
        rtext(page, 450, y, fmt_money(it["unit_price"]))
        rtext(page, 555, y, fmt_money(it["line_total"]))
        y += 20
    page.draw_line(fitz.Point(40, y - 8), fitz.Point(555, y - 8), color=(0.8, 0.8, 0.8))

    y += 10
    rows = [("Net Amount", inv["subtotal"]), (tax_label(inv, "GST"), inv["tax"])]
    for label, val in rows:
        if val is not None:
            text(page, 360, y, label)
            rtext(page, 555, y, fmt_money(val))
            y += 18
    if inv["total"] is not None:
        page.draw_rect(fitz.Rect(350, y - 6, 560, y + 18), color=None, fill=(0.9, 0.96, 0.96))
        text(page, 360, y + 10, "Grand Total", 11, "hebo", accent)
        rtext(page, 555, y + 10, fmt_money(inv["total"]), 11, "hebo", accent)


def render_receipt(page, inv):
    """Narrow, monospaced, receipt-style bill."""
    v = inv["vendor"]
    x, width, size = 170, 270, 9
    sep = "-" * 44

    def line(s, y, bold=False):
        text(page, x, y, s, size, "cobo" if bold else "cour")

    def lr(left, right, y, bold=False):
        line(left, y, bold)
        rtext(page, x + width, y, right, size, "cobo" if bold else "cour")

    y = 60
    line(v["name"], y, True); y += 13
    line(v["city"], y); y += 13
    line(sep, y); y += 14
    if inv["invoice_number"]:
        lr("Bill#", inv["invoice_number"], y); y += 13
    if d := date_text(inv, "invoice_date", "receipt"):
        lr("Date", d, y); y += 13
    if d := date_text(inv, "due_date", "receipt"):
        lr("Pay by", d, y); y += 13
    line(sep, y); y += 14
    for it in inv["items"]:
        line(it["name"][:40], y); y += 12
        lr(f"  {it['qty']} x {fmt_money(it['unit_price'])}", fmt_money(it["line_total"]), y); y += 14
    line(sep, y); y += 14
    if inv["subtotal"] is not None:
        lr("SUBTOTAL", fmt_money(inv["subtotal"]), y); y += 13
    if inv["tax"] is not None:
        lr(tax_label(inv, "TAX").upper(), fmt_money(inv["tax"]), y); y += 13
    if inv["total"] is not None:
        cur = f"{inv['currency']} " if inv["currency"] else ""
        lr("TOTAL", f"{cur}{fmt_money(inv['total'])}", y, True); y += 13
    elif inv["currency"]:
        lr("CURRENCY", inv["currency"], y); y += 13
    line(sep, y); y += 14
    line("   ** THANK YOU **", y)


RENDERERS = {
    "classic": render_classic,
    "table": render_table,
    "modern": render_modern,
    "receipt": render_receipt,
}


# --------------------------------------------------------------------------- #
# Driver
# --------------------------------------------------------------------------- #
def write_fixed_examples(output):
    for filename, lines in EXAMPLES.items():
        doc = fitz.open()
        page = doc.new_page()
        y = 80
        for line in lines:
            page.insert_text((72, y), line, fontsize=10)
            y += 24
        doc.save(output / filename)
        doc.close()


def plan_scenarios(rng, count, allowed):
    """Cycle through scenarios so each appears, then shuffle; never start with a duplicate."""
    plan = [allowed[i % len(allowed)] for i in range(count)]
    rng.shuffle(plan)
    if plan and plan[0] == "duplicate_id":
        swap = next((i for i, s in enumerate(plan) if s != "duplicate_id"), None)
        if swap is not None:
            plan[0], plan[swap] = plan[swap], plan[0]
    return plan


def generate_random(output, count, rng, scenarios, include_fixed_numbers):
    for old in output.glob("rand_*.pdf"):
        old.unlink()

    used = list(FIXED_NUMBERS) if include_fixed_numbers else []
    counters = {v["prefix"]: rng.randint(1000, 8000) for v in VENDORS}
    vendors_by_name = {v["name"]: v for v in VENDORS}
    manifest = []

    for idx, scenario in enumerate(plan_scenarios(rng, count, scenarios), start=1):
        if scenario == "duplicate_id" and used:
            vendor_name, number = rng.choice(used)
            vendor = vendors_by_name[vendor_name]
        else:
            if scenario == "duplicate_id":  # nothing to duplicate yet
                scenario = "valid"
            vendor = rng.choice(VENDORS)
            counters[vendor["prefix"]] += rng.randint(1, 9)
            number = f"{vendor['prefix']}-{counters[vendor['prefix']]}"

        inv = build_valid_invoice(rng, vendor, number)
        expected = expected_values(inv)

        if scenario == "missing_field":
            detail = apply_missing_field(rng, inv)
        elif scenario == "arithmetic_mismatch":
            detail = apply_arithmetic_mismatch(rng, inv)
        elif scenario == "invalid_date":
            detail = apply_invalid_date(rng, inv)
        elif scenario == "duplicate_id":
            detail = f"invoice number {number} already used by {vendor['name']}"
        else:
            detail = "all fields present and arithmetic correct"

        if scenario != "duplicate_id" and inv["invoice_number"]:
            used.append((vendor["name"], number))

        layout = rng.choice(LAYOUTS)
        filename = f"rand_{idx:03d}_{scenario}.pdf"
        doc = fitz.open()
        page = doc.new_page()  # A4-ish default (595 x 842)
        RENDERERS[layout](page, inv)
        doc.set_metadata({"title": f"Invoice {inv['invoice_number'] or ''}".strip(),
                          "author": vendor["name"], "subject": "Fictional test invoice"})
        doc.save(output / filename)
        doc.close()

        manifest.append({"file": filename, "scenario": scenario, "detail": detail,
                         "layout": layout, "expected": expected})

    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Generate fictional test invoice PDFs.")
    parser.add_argument("--count", type=int, default=20, help="number of random invoices (default 20)")
    parser.add_argument("--seed", type=int, default=None, help="random seed for reproducible output")
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=SCENARIOS,
                        help="restrict random invoices to these scenarios")
    parser.add_argument("--no-fixed", action="store_true", help="skip the six fixed example PDFs")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(exist_ok=True)
    rng = random.Random(args.seed)

    if not args.no_fixed:
        write_fixed_examples(OUTPUT_DIR)
        print(f"Generated {len(EXAMPLES)} fixed PDFs in {OUTPUT_DIR}")

    manifest = generate_random(OUTPUT_DIR, args.count, rng, args.scenarios, not args.no_fixed)
    summary = {}
    for entry in manifest:
        summary[entry["scenario"]] = summary.get(entry["scenario"], 0) + 1
    print(f"Generated {len(manifest)} random PDFs in {OUTPUT_DIR}: "
          + ", ".join(f"{k}={v}" for k, v in sorted(summary.items())))
    print(f"Manifest written to {OUTPUT_DIR / 'manifest.json'}")


if __name__ == "__main__":
    main()
