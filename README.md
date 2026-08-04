# Invoice Document Automation Dashboard

A portfolio-ready FastAPI application for extracting structured invoice data from PDF files, reviewing low-confidence records, detecting duplicates, and exporting clean accounting datasets to CSV and Excel.

![Dashboard](docs/screenshots/dashboard.png)

## Business problem

Finance and operations teams often receive invoices as PDF files and manually copy vendor names, invoice numbers, dates, tax, and totals into spreadsheets. This project automates the repetitive part while keeping a human review step for uncertain records.

## Features

- Batch upload of PDF invoices
- PDF text extraction with PyMuPDF
- Rule-based field extraction
- Vendor, invoice number, invoice date, due date, currency, subtotal, tax, and total
- Weighted confidence scoring
- Manual review and editing workflow
- Duplicate detection by file hash and vendor/invoice number
- SQLite processing history
- Search and status filters
- CSV and formatted Excel exports
- REST API and Swagger documentation
- Demo invoice generator
- Automated tests

## Tech stack

Python, FastAPI, SQLAlchemy, SQLite, PyMuPDF, Jinja2, Pandas, OpenPyXL, ReportLab, Pytest.

## Quick start on Windows

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python seed_demo.py
python run.py
```

Open:

- Dashboard: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Run tests

```bat
pytest -q
```

## Typical workflow

1. Upload one or more PDF invoices.
2. The parser extracts structured fields and calculates confidence.
3. Low-confidence records enter the review queue.
4. Duplicate invoices are flagged.
5. Approved data is exported to CSV or Excel.

## Portfolio positioning

This is a personal demonstration project built to showcase document automation, PDF data extraction, backend development, data validation, and Excel reporting. It does not claim to be client work.

## Future production improvements

- OCR for scanned invoices
- Vendor-specific extraction templates
- LLM-assisted extraction fallback
- User authentication and roles
- Cloud storage
- Background job queue
- Accounting-platform integrations
