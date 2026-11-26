# FinalCapstone_team6 — AI-Powered Invoice Processing & Approval

This repo is the team project for EY Capstone Project 06. It has a React frontend, a FastAPI backend and a PostgreSQL database.
This README covers the **database setup**. You create the database, all of its tables and some fictional sample rows with one command.

## Project layout

```
backend/
  database.py      # Connects to PostgreSQL (SQLAlchemy engine, SessionLocal, Base, get_db)
  models.py        # Table definitions (SQLAlchemy ORM)
  init_db.py       # Creates the database and tables, then inserts sample data
  sql/queries.sql  # The SQL queries the spec asks us to demonstrate
  requirements.txt
  .env.example     # Template for your local backend/.env (do not commit .env)
frontend/
```

## Prerequisites

- **PostgreSQL 14 or later** running on `localhost:5432`.
  - On Windows, open `services.msc` and start **postgresql-x64-16**. You can also run `net start postgresql-x64-16` from an *Administrator* terminal.
- **Python 3.10 or later**

## Setup

```bash
# 1. Go to the backend folder
cd backend

# 2. (Recommended) Create and activate a virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS/Linux

# 3. Install the dependencies
pip install -r requirements.txt

# 4. Set up your connection details
copy .env.example .env          # Windows  (cp on macOS/Linux)
#    Edit .env and set DB_PASSWORD to your local postgres password.
#    The team's default local setup uses: DB_NAME=invoice_processing, DB_PASSWORD=Admin@123

# 5. Create the database and tables, and insert the sample data
python init_db.py
```

You do **not** need to create the `invoice_processing` database by hand. `init_db.py` connects to the default `postgres` database and creates it if it is missing.

Expected output:

```
Created database 'invoice_processing'.
Connected: PostgreSQL 16.x
Tables ready: approvers, auditors, clerks, extraction_runs, invoice_approvals, invoice_checks, invoice_corrections, invoice_files, invoice_items, invoices, vendors
  vendors              3 rows
  invoices             7 rows
  ...
Seed data inserted.
```

### Re-running

| Command | Effect |
|---|---|
| `python init_db.py` | Safe to run again. It creates any missing tables and inserts the sample data only when the tables are empty. |
| `python init_db.py --reset` | **Deletes all tables and data**, then recreates the tables and inserts the sample data again. |
| `python init_db.py --no-seed` | Creates the tables without any sample data. |

## Using the connection in FastAPI

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from database import get_db
from models import Vendor

@app.get("/vendors")
def list_vendors(db: Session = Depends(get_db)):
    return db.query(Vendor).all()
```

## Data model

```
vendors 1───* invoices 1───* invoice_items
                  │  1───* invoice_checks
                  │  1───* extraction_runs      (raw AI output, never overwritten)
                  │  1───* invoice_corrections  (clerk edits: old → new value)
                  │  1───* invoice_approvals    (human decisions, append-only)
                  │  1───1 invoice_files        (compressed PDF bytes, <= 1 MB)
                  └── duplicate_of_invoice_id → invoices (self-reference for flagged duplicates)
```

| Table | Purpose |
|---|---|
| `clerks` / `approvers` | Login accounts for the two active roles (argon2-hashed passwords). |
| `auditors` | Login accounts for the read-only auditor role (trace extraction, corrections and decisions). No API endpoints use it yet. |
| `vendors` | Vendor master records: name (unique), contact reference, tax id and an active flag. |
| `invoices` | One row per uploaded PDF. Stores the source file reference (`file_path`, `original_filename`, `file_size_bytes`) separately from the current verified fields (number, dates, subtotal, tax, total). Also stores `status` and `is_verified`. |
| `invoice_items` | Line items. `line_total` is the amount printed on the document. The app recalculates `quantity × unit_price` itself. |
| `invoice_checks` | Results of the rule-based checks: `duplicate`, `line_total`, `invoice_total`, `missing_field` and `text_readable`. Each result is `pass`, `fail` or `warning`. |
| `extraction_runs` | Each AI extraction attempt: the JSON it returned, provider, model, status (`success`/`partial`/`failed`/`no_text`/`timeout`/`rate_limited`), any error and how long it took. |
| `invoice_corrections` | Audit trail of clerk corrections. The original AI value stays in `extraction_runs`. |
| `invoice_approvals` | Approver decisions (`approved`/`rejected`), each with a required note. |
| `invoice_files` | The uploaded PDF itself, compressed with PyMuPDF and stored as `BYTEA`. A CHECK constraint caps it at 1 MB. |

Constraints the database enforces:

- **Duplicates:** a partial unique index makes `(vendor_id, invoice_number)` unique among non-duplicate invoices. A re-uploaded duplicate is still saved as its own row, with `duplicate_of_invoice_id` pointing at the original. The original row is never overwritten.
- **Allowed values:** CHECK constraints limit statuses, check types and decisions to known values. They also reject negative amounts and zero or negative quantities.
- **Foreign keys:** vendors that have invoices cannot be deleted. Invoices that have approvals cannot be deleted.

## Sample data

The sample data is fictional and covers the test scenarios from the spec:

| # | Vendor | Invoice | Scenario | Status |
|---|---|---|---|---|
| 1 | Acme Office Supplies | INV-1001 | Valid invoice, all checks pass | approved |
| 2 | Acme Office Supplies | INV-1002 | **Line-total mismatch** (50 × 1.20 printed as 65.00) | discrepancy |
| 3 | Acme Office Supplies | INV-1002 | **Duplicate invoice number** for the same vendor | discrepancy |
| 4 | Nimbus Cloud Services | NCS-2026-077 | **Missing tax and total** | discrepancy |
| 5 | Nimbus Cloud Services | NCS-2026-078 | Valid, waiting for the approver | pending_approval |
| 6 | BlueRiver Logistics | BRL-5531 | **Clerk corrected** the AI-read date, then the approver rejected it with a note | rejected |
| 7 | BlueRiver Logistics | — | **Scanned or unreadable PDF**: no text, needs manual entry | uploaded |

> The `file_path` values (`uploads/invoice_000N.pdf`) are placeholder references. The sample PDFs are not included yet.

## Required SQL demonstrations

```bash
psql -U postgres -d invoice_processing -f sql/queries.sql
```

This runs:

1. Invoices joined with vendors, with each invoice's latest approval status
2. Invoice totals by vendor, with pending counts
3. Discrepancy list: failed duplicate, missing-field and arithmetic checks

## Running the app (backend + frontend)

```bash
# Terminal 1: backend API on http://127.0.0.1:8000
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload       # backend/.env must define JWT_SECRET_KEY

# Terminal 2: frontend on http://localhost:5173
cd frontend
npm install
npm run dev
```

The frontend is **React + Vite + Tailwind CSS v4** and follows `DESIGN.md`. In development, Vite proxies every `/api/*` request to the backend, so the backend needs no CORS setup. If the backend runs on another address, set `VITE_BACKEND_URL` in `frontend/.env.local` (see `frontend/.env.example`). In development, the login page shows one-click demo accounts for the seeded users.

| Role | Pages |
|---|---|
| Clerk | Invoice list with status/vendor filters · Upload a PDF (optionally running AI extraction straight away) · Review and correct the extracted data, with live arithmetic checks · Submit for approval · Vendor management |
| Approver | Approval queue · Invoice detail with line items, validation checks, correction/extraction history and the AI summary · Approve or reject with a required note |
| Auditor | All submitted invoices with status tabs and CSV export · Full trail per invoice: timeline, items, checks, corrections, raw AI runs, decisions |

```
frontend/src/
  api/client.js        fetch wrapper: JWT header, FastAPI error parsing, 401 → logout
  api/endpoints.js     one function per backend endpoint (update here when the API changes)
  auth/                AuthContext (login, /auth/me, logout) and role route guards
  components/ui.jsx    design-system primitives (Button, Hero, Table, Tabs, Modal, …)
  components/invoice.jsx  shared invoice views (summary, items, checks, history timeline)
  pages/clerk|approver|auditor/
```

## Troubleshooting

- **`Connection refused` on port 5432**: the PostgreSQL service is not running. Start it (see Prerequisites).
- **`password authentication failed for user "postgres"`**: `DB_PASSWORD` in `backend/.env` does not match your local install.
- **Password contains `@` or other special characters**: no change needed. `database.py` builds the connection URL with `URL.create`, which handles them.
