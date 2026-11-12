# Upwork Portfolio Entry

## Title

Invoice & PDF Data Extraction Dashboard with Review Workflow and Excel Export

## Description

Developed a FastAPI document automation dashboard that turns PDF invoices into structured accounting data and is honest about what it could not read.

The application extracts vendor, invoice number, dates, currency, subtotal, tax, and total from the PDF text, including US and European number formats and ambiguous dates. Each invoice gets a confidence score that drops when fields are missing, when subtotal plus tax does not equal the total, or when a date cannot be read. Uncertain invoices go to a review page that shows the reasons and the original PDF side by side. Duplicates are detected by file hash and by vendor plus invoice number, value is totaled per currency, and clean datasets are exported to CSV and formatted Excel, with protection against spreadsheet formula injection.

## My contribution

- Designed the extraction rules, the confidence model, and the review workflow
- Built PDF text extraction with PyMuPDF and the amount and date parsing
- Implemented duplicate detection, per-currency reporting, search, filters, and pagination
- Developed the FastAPI backend, JSON API, and the responsive interface with light and dark themes
- Added an upload pipeline with per-file results, size limits, and stored originals
- Wrote 110 automated tests and CI on Python 3.11 and 3.12

## Technologies

Python, FastAPI, SQLAlchemy, SQLite, PyMuPDF, pandas, openpyxl, Jinja2, ReportLab, pytest, Docker, GitHub Actions

## Skills demonstrated

PDF data extraction, document automation, invoice processing, data validation, duplicate detection, FastAPI development, Excel automation, SQLite, REST APIs, test-driven quality.
