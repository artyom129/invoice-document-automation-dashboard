# Invoice Document Automation Dashboard

[English](README.md) | **Русский**

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
