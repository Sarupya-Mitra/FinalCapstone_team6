"""Generate six short, TEXT-BASED fictional PDFs for the required test cases.

Run: python sample_data/create_sample_invoices.py
Outputs to sample_data/pdfs/. No scanned images or real banking information.
"""

from pathlib import Path

import fitz

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


def main():
    output = Path(__file__).parent / "pdfs"
    output.mkdir(exist_ok=True)
    for filename, lines in EXAMPLES.items():
        doc = fitz.open()
        page = doc.new_page()
        y = 80
        for line in lines:
            page.insert_text((72, y), line, fontsize=10)
            y += 24
        doc.save(output / filename)
        doc.close()
    print(f"Generated {len(EXAMPLES)} PDFs in {output}")


if __name__ == "__main__":
    main()
