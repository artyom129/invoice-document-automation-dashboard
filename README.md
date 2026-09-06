<a id="english"></a>

<div align="center">

**🇬🇧 English** · [🇷🇺 Русский](#russian)

</div>

# Invoice Document Automation Dashboard

A portfolio-ready FastAPI application for extracting structured invoice data from PDF files, reviewing low-confidence records, detecting duplicates, and exporting clean accounting datasets to CSV and Excel.

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

---

<a id="russian"></a>

<div align="center">

[🇬🇧 English](#english) · **🇷🇺 Русский**

</div>

# Invoice Document Automation Dashboard — Русская версия

FastAPI-приложение для автоматического извлечения структурированных данных из PDF-счетов, проверки сомнительных записей, поиска дублей и экспорта готовых бухгалтерских данных в CSV/Excel.

## Зачем нужен проект

Финансовые и операционные команды часто вручную переносят из PDF название поставщика, номер счёта, даты, налог и итоговую сумму в таблицы. Этот проект автоматизирует повторяющуюся часть процесса, но оставляет ручную проверку для записей с низкой уверенностью.

## Возможности

- пакетная загрузка PDF-счетов;
- извлечение текста через PyMuPDF;
- rule-based извлечение полей;
- vendor, invoice number, invoice date, due date, currency, subtotal, tax, total;
- weighted confidence score;
- очередь ручной проверки и редактирования;
- поиск дублей по file hash и vendor/invoice number;
- история обработки в SQLite;
- поиск и фильтры по статусу;
- экспорт в CSV и форматированный Excel;
- REST API и Swagger;
- генератор demo-счетов;
- автоматические тесты.

## Стек

Python, FastAPI, SQLAlchemy, SQLite, PyMuPDF, Jinja2, Pandas, OpenPyXL, ReportLab, Pytest.

## Запуск на Windows

```bat
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python seed_demo.py
python run.py
```

Открыть:

- Dashboard: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`
- Health: `http://localhost:8000/health`

## Типовой процесс

1. Загрузить один или несколько PDF.
2. Парсер извлекает поля и рассчитывает confidence.
3. Неуверенные записи попадают в review queue.
4. Дубли помечаются.
5. Подтверждённые данные экспортируются в CSV/Excel.

## Дальнейшее развитие

OCR для сканов, шаблоны под поставщиков, LLM fallback, роли и авторизация, cloud storage, background jobs и интеграции с бухгалтерскими системами.

Проект демонстрирует document automation, PDF extraction, backend-разработку, валидацию данных и Excel-отчётность.
