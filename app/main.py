from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi import Depends, FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import Settings
from .database import build_engine, build_session_factory, ensure_schema
from .extractor import parse_amount, parse_date
from .models import STATUSES, Invoice
from .processing import process_upload, stored_path
from .services import escape_like, export_csv, export_excel

APP_DIR = Path(__file__).resolve().parent
EDITABLE_STATUSES = STATUSES
templates = Jinja2Templates(directory=str(APP_DIR / "templates"))


def get_db(request: Request):
    db = request.app.state.SessionLocal()
    try:
        yield db
    finally:
        db.close()


def filtered(db: Session, status: str | None, q: str | None):
    """The invoice query behind the dashboard, the API, and the exports."""
    query = select(Invoice)
    if status in STATUSES:
        query = query.where(Invoice.status == status)
    if q and q.strip():
        pattern = f"%{escape_like(q.strip())}%"
        query = query.where(
            Invoice.vendor.ilike(pattern, escape="\\")
            | Invoice.invoice_number.ilike(pattern, escape="\\")
            | Invoice.filename.ilike(pattern, escape="\\")
        )
    return query


def dashboard_stats(db: Session) -> dict:
    counts = dict(db.execute(select(Invoice.status, func.count(Invoice.id)).group_by(Invoice.status)).all())
    # Value is summed per currency and leaves out duplicates and rejected invoices,
    # so a EUR invoice is never added to a USD one.
    totals = db.execute(
        select(Invoice.currency, func.sum(Invoice.total))
        .where(Invoice.is_duplicate.is_(False), Invoice.status.in_(("approved", "review")), Invoice.total.is_not(None))
        .group_by(Invoice.currency)
        .order_by(func.sum(Invoice.total).desc())
    ).all()
    return {
        "total": sum(counts.values()),
        "approved": counts.get("approved", 0),
        "review": counts.get("review", 0),
        "duplicate": counts.get("duplicate", 0),
        "rejected": counts.get("rejected", 0),
        "value_by_currency": [{"currency": currency or "unknown", "total": round(total or 0, 2)} for currency, total in totals],
    }


def invoice_dict(invoice: Invoice) -> dict:
    return {
        "id": invoice.id,
        "filename": invoice.filename,
        "vendor": invoice.vendor,
        "invoice_number": invoice.invoice_number,
        "invoice_date": invoice.invoice_date,
        "due_date": invoice.due_date,
        "currency": invoice.currency,
        "subtotal": invoice.subtotal,
        "tax": invoice.tax,
        "total": invoice.total,
        "confidence": invoice.confidence,
        "status": invoice.status,
        "is_duplicate": invoice.is_duplicate,
        "duplicate_of_id": invoice.duplicate_of_id,
        "issues": invoice.issues,
        "notes": invoice.notes,
        "created_at": invoice.created_at.isoformat() if invoice.created_at else None,
    }


def get_invoice_or_404(db: Session, invoice_id: int) -> Invoice:
    invoice = db.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="Invoice not found.")
    return invoice


def clear_duplicate_flag(invoice: Invoice) -> None:
    invoice.is_duplicate = False
    invoice.duplicate_of_id = None


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    engine = build_engine(settings.database_url)
    ensure_schema(engine)
    settings.upload_dir.mkdir(parents=True, exist_ok=True)

    app = FastAPI(
        title="Invoice Document Automation Dashboard",
        version="1.1.0",
        description="Upload PDF invoices, extract structured fields, review duplicates, and export clean data.",
    )
    app.state.settings = settings
    app.state.engine = engine
    app.state.SessionLocal = build_session_factory(engine)
    app.mount("/static", StaticFiles(directory=str(APP_DIR / "static")), name="static")

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        """Browsers get a readable page, API clients get JSON."""
        wants_html = "text/html" in request.headers.get("accept", "")
        if wants_html and not request.url.path.startswith(("/api/", "/health")):
            return templates.TemplateResponse(
                request=request,
                name="error.html",
                context={"status_code": exc.status_code, "message": exc.detail},
                status_code=exc.status_code,
            )
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.get("/health", tags=["System"])
    def health(db: Session = Depends(get_db)):
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            return JSONResponse({"status": "error", "database": "unreachable"}, status_code=503)
        return {"status": "ok", "service": "Invoice Document Automation Dashboard", "database": "ok"}

    # ------------------------------------------------------------------ pages

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def dashboard(
        request: Request,
        status: str | None = None,
        q: str | None = None,
        page: int = Query(1, ge=1),
        db: Session = Depends(get_db),
    ):
        query = filtered(db, status, q)
        matching = db.scalar(select(func.count()).select_from(query.subquery())) or 0
        size = settings.page_size
        invoices = db.scalars(query.order_by(Invoice.created_at.desc(), Invoice.id.desc()).offset((page - 1) * size).limit(size)).all()
        return templates.TemplateResponse(
            request=request,
            name="dashboard.html",
            context={
                "invoices": invoices,
                "stats": dashboard_stats(db),
                "selected_status": status if status in STATUSES else "",
                "q": q or "",
                "page": page,
                "matching": matching,
                "has_next": page * size < matching,
                "statuses": STATUSES,
            },
        )

    @app.get("/upload", response_class=HTMLResponse, include_in_schema=False)
    def upload_page(request: Request):
        return templates.TemplateResponse(
            request=request,
            name="upload.html",
            context={"results": None, "max_mb": settings.max_upload_bytes / (1024 * 1024)},
        )

    @app.post("/upload", response_class=HTMLResponse, include_in_schema=False)
    async def upload_invoices(request: Request, db: Session = Depends(get_db)):
        # Read the raw form: a browser that submits with nothing chosen sends an
        # empty file part, which would fail validation instead of giving a message.
        form = await request.form()
        results = []
        for file in form.getlist("files"):
            if not hasattr(file, "filename") or not file.filename:
                continue
            # Read one byte past the limit: enough to know the file is too big without loading all of it.
            data = await file.read(settings.max_upload_bytes + 1)
            results.append(process_upload(db, settings, file.filename, data))
        summary = {
            "processed": sum(1 for r in results if r.result == "processed"),
            "approved": sum(1 for r in results if r.result == "processed" and r.detail == "approved"),
            "review": sum(1 for r in results if r.result == "processed" and r.detail == "review"),
            "duplicate": sum(1 for r in results if r.result == "processed" and r.detail == "duplicate"),
            "already_uploaded": sum(1 for r in results if r.result == "already_uploaded"),
            "skipped": sum(1 for r in results if r.result == "skipped"),
        }
        return templates.TemplateResponse(
            request=request,
            name="upload.html",
            context={"results": results, "summary": summary, "max_mb": settings.max_upload_bytes / (1024 * 1024)},
        )

    def render_detail(request: Request, db: Session, invoice: Invoice, *, error: str | None = None, form: dict | None = None, status_code: int = 200):
        duplicate = db.get(Invoice, invoice.duplicate_of_id) if invoice.duplicate_of_id else None
        return templates.TemplateResponse(
            request=request,
            name="invoice_detail.html",
            context={
                "invoice": invoice,
                "duplicate": duplicate,
                "pdf_available": stored_path(settings, invoice.file_hash).exists(),
                "error": error,
                "form": form or {},
                "statuses": EDITABLE_STATUSES,
            },
            status_code=status_code,
        )

    @app.get("/invoices/{invoice_id}", response_class=HTMLResponse, include_in_schema=False)
    def invoice_detail(invoice_id: int, request: Request, db: Session = Depends(get_db)):
        return render_detail(request, db, get_invoice_or_404(db, invoice_id))

    @app.get("/invoices/{invoice_id}/pdf", tags=["Invoices"])
    def invoice_pdf(invoice_id: int, db: Session = Depends(get_db)):
        invoice = get_invoice_or_404(db, invoice_id)
        path = stored_path(settings, invoice.file_hash)
        if not path.exists():
            raise HTTPException(status_code=404, detail="The original PDF is not stored.")
        return FileResponse(path, media_type="application/pdf", filename=invoice.filename, content_disposition_type="inline")

    @app.post("/invoices/{invoice_id}/update", include_in_schema=False)
    def update_invoice(
        invoice_id: int,
        request: Request,
        vendor: str = Form(""),
        invoice_number: str = Form(""),
        invoice_date: str = Form(""),
        due_date: str = Form(""),
        currency: str = Form(""),
        subtotal: str = Form(""),
        tax: str = Form(""),
        total: str = Form(""),
        status: str = Form("review"),
        notes: str = Form(""),
        db: Session = Depends(get_db),
    ):
        invoice = get_invoice_or_404(db, invoice_id)
        form = {
            "vendor": vendor, "invoice_number": invoice_number, "invoice_date": invoice_date, "due_date": due_date,
            "currency": currency, "subtotal": subtotal, "tax": tax, "total": total, "status": status, "notes": notes,
        }

        errors: list[str] = []
        amounts: dict[str, float | None] = {}
        for name, raw in (("subtotal", subtotal), ("tax", tax), ("total", total)):
            if not raw.strip():
                amounts[name] = None
                continue
            value = parse_amount(raw)
            if value is None:
                errors.append(f"{name.capitalize()} “{raw.strip()}” is not a number.")
            amounts[name] = value

        dates: dict[str, str | None] = {}
        for name, raw in (("invoice_date", invoice_date), ("due_date", due_date)):
            if not raw.strip():
                dates[name] = None
                continue
            iso, _ = parse_date(raw)
            if iso is None:
                errors.append(f"{name.replace('_', ' ').capitalize()} “{raw.strip()}” must look like 2026-07-22.")
            dates[name] = iso

        if status not in EDITABLE_STATUSES:
            errors.append(f"Status must be one of: {', '.join(EDITABLE_STATUSES)}.")
        if currency.strip() and not (len(currency.strip()) == 3 and currency.strip().isalpha()):
            errors.append("Currency must be a three-letter code such as USD.")

        if errors:
            return render_detail(request, db, invoice, error=" ".join(errors), form=form, status_code=400)

        invoice.vendor = vendor.strip() or None
        invoice.invoice_number = invoice_number.strip() or None
        invoice.invoice_date = dates["invoice_date"]
        invoice.due_date = dates["due_date"]
        invoice.currency = currency.strip().upper() or None
        invoice.subtotal = amounts["subtotal"]
        invoice.tax = amounts["tax"]
        invoice.total = amounts["total"]
        invoice.status = status
        invoice.notes = notes.strip()
        if status == "duplicate":
            invoice.is_duplicate = True
        else:
            clear_duplicate_flag(invoice)
        db.commit()
        return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)

    @app.post("/invoices/{invoice_id}/approve", include_in_schema=False)
    def approve_invoice(invoice_id: int, db: Session = Depends(get_db)):
        invoice = get_invoice_or_404(db, invoice_id)
        invoice.status = "approved"
        clear_duplicate_flag(invoice)  # approving means a person decided this is not a duplicate
        db.commit()
        return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)

    @app.post("/invoices/{invoice_id}/reject", include_in_schema=False)
    def reject_invoice(invoice_id: int, db: Session = Depends(get_db)):
        invoice = get_invoice_or_404(db, invoice_id)
        invoice.status = "rejected"
        db.commit()
        return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)

    # -------------------------------------------------------------------- API

    @app.get("/api/invoices", tags=["JSON API"])
    def api_invoices(
        status: str | None = None,
        q: str | None = None,
        limit: int = Query(100, ge=1, le=500),
        offset: int = Query(0, ge=0),
        db: Session = Depends(get_db),
    ):
        query = filtered(db, status, q).order_by(Invoice.created_at.desc(), Invoice.id.desc()).offset(offset).limit(limit)
        return [invoice_dict(invoice) for invoice in db.scalars(query).all()]

    @app.get("/api/invoices/{invoice_id}", tags=["JSON API"])
    def api_invoice(invoice_id: int, db: Session = Depends(get_db)):
        return invoice_dict(get_invoice_or_404(db, invoice_id))

    @app.get("/api/stats", tags=["JSON API"])
    def api_stats(db: Session = Depends(get_db)):
        return dashboard_stats(db)

    # ---------------------------------------------------------------- exports

    def export_rows(db: Session, status: str | None, q: str | None) -> list[Invoice]:
        return list(db.scalars(filtered(db, status, q).order_by(Invoice.created_at.desc(), Invoice.id.desc())).all())

    @app.get("/export.csv", tags=["Exports"])
    def download_csv(status: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
        return StreamingResponse(
            BytesIO(export_csv(export_rows(db, status, q))),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=invoices.csv"},
        )

    @app.get("/export.xlsx", tags=["Exports"])
    def download_excel(status: str | None = None, q: str | None = None, db: Session = Depends(get_db)):
        return StreamingResponse(
            BytesIO(export_excel(export_rows(db, status, q))),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": "attachment; filename=invoices.xlsx"},
        )

    return app


app = create_app()
