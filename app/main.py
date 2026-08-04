from __future__ import annotations

import shutil
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func
from sqlalchemy.orm import Session

from .database import Base, engine, get_db
from .extractor import extract_invoice_fields, extract_pdf_text
from .models import Invoice
from .services import export_csv, export_excel, find_duplicate, sha256_file

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Invoice Document Automation Dashboard",
    version="1.0.0",
    description="Upload PDF invoices, extract structured fields, review duplicates, and export clean data.",
)

app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "app" / "templates")

@app.get("/health")
def health():
    return {"status": "ok", "service": "Invoice Document Automation Dashboard"}

@app.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    status: str | None = None,
    q: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Invoice)
    if status:
        query = query.filter(Invoice.status == status)
    if q:
        wildcard = f"%{q}%"
        query = query.filter(
            (Invoice.vendor.ilike(wildcard))
            | (Invoice.invoice_number.ilike(wildcard))
            | (Invoice.filename.ilike(wildcard))
        )
    invoices = query.order_by(Invoice.created_at.desc()).all()

    total_count = db.query(func.count(Invoice.id)).scalar() or 0
    approved_count = db.query(func.count(Invoice.id)).filter(Invoice.status == "approved").scalar() or 0
    review_count = db.query(func.count(Invoice.id)).filter(Invoice.status == "review").scalar() or 0
    duplicate_count = db.query(func.count(Invoice.id)).filter(Invoice.is_duplicate.is_(True)).scalar() or 0
    total_value = db.query(func.coalesce(func.sum(Invoice.total), 0)).filter(Invoice.is_duplicate.is_(False)).scalar() or 0

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={
            "invoices": invoices,
            "total_count": total_count,
            "approved_count": approved_count,
            "review_count": review_count,
            "duplicate_count": duplicate_count,
            "total_value": total_value,
            "selected_status": status or "",
            "q": q or "",
        },
    )

@app.get("/upload", response_class=HTMLResponse)
def upload_page(request: Request):
    return templates.TemplateResponse(request=request, name="upload.html", context={})

@app.post("/upload")
async def upload_invoices(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
):
    uploaded = 0
    for file in files:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix != ".pdf":
            continue

        safe_name = f"{uuid.uuid4().hex}{suffix}"
        target = UPLOAD_DIR / safe_name
        with target.open("wb") as output:
            shutil.copyfileobj(file.file, output)

        file_hash = sha256_file(target)
        existing_hash = db.query(Invoice).filter(Invoice.file_hash == file_hash).first()
        if existing_hash:
            target.unlink(missing_ok=True)
            continue

        raw_text = extract_pdf_text(target)
        fields = extract_invoice_fields(raw_text)
        duplicate = find_duplicate(
            db,
            file_hash=file_hash,
            vendor=fields.get("vendor"),
            invoice_number=fields.get("invoice_number"),
        )

        status = "duplicate" if duplicate else ("approved" if fields["confidence"] >= 80 else "review")
        invoice = Invoice(
            filename=file.filename or safe_name,
            file_hash=file_hash,
            vendor=fields.get("vendor"),
            invoice_number=fields.get("invoice_number"),
            invoice_date=fields.get("invoice_date"),
            due_date=fields.get("due_date"),
            currency=fields.get("currency"),
            subtotal=fields.get("subtotal"),
            tax=fields.get("tax"),
            total=fields.get("total"),
            confidence=fields["confidence"],
            status=status,
            is_duplicate=bool(duplicate),
            duplicate_of_id=duplicate.id if duplicate else None,
            raw_text=raw_text,
        )
        db.add(invoice)
        db.commit()
        uploaded += 1

    return RedirectResponse(url=f"/?uploaded={uploaded}", status_code=303)

@app.get("/invoices/{invoice_id}", response_class=HTMLResponse)
def invoice_detail(
    invoice_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    duplicate = db.get(Invoice, invoice.duplicate_of_id) if invoice.duplicate_of_id else None
    return templates.TemplateResponse(
        request=request,
        name="invoice_detail.html",
        context={"invoice": invoice, "duplicate": duplicate},
    )

@app.post("/invoices/{invoice_id}/update")
def update_invoice(
    invoice_id: int,
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
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    def number(value: str):
        value = value.strip().replace(",", "")
        return float(value) if value else None

    invoice.vendor = vendor.strip() or None
    invoice.invoice_number = invoice_number.strip() or None
    invoice.invoice_date = invoice_date.strip() or None
    invoice.due_date = due_date.strip() or None
    invoice.currency = currency.strip().upper() or None
    invoice.subtotal = number(subtotal)
    invoice.tax = number(tax)
    invoice.total = number(total)
    invoice.status = status
    invoice.notes = notes.strip()
    db.commit()
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)

@app.post("/invoices/{invoice_id}/approve")
def approve_invoice(invoice_id: int, db: Session = Depends(get_db)):
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice.status = "approved"
    db.commit()
    return RedirectResponse(url=f"/invoices/{invoice_id}", status_code=303)

@app.get("/api/invoices")
def api_invoices(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return [
        {
            "id": i.id,
            "filename": i.filename,
            "vendor": i.vendor,
            "invoice_number": i.invoice_number,
            "invoice_date": i.invoice_date,
            "due_date": i.due_date,
            "currency": i.currency,
            "subtotal": i.subtotal,
            "tax": i.tax,
            "total": i.total,
            "confidence": i.confidence,
            "status": i.status,
            "is_duplicate": i.is_duplicate,
        }
        for i in invoices
    ]

@app.get("/export.csv")
def download_csv(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return StreamingResponse(
        BytesIO(export_csv(invoices)),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=invoices.csv"},
    )

@app.get("/export.xlsx")
def download_excel(db: Session = Depends(get_db)):
    invoices = db.query(Invoice).order_by(Invoice.created_at.desc()).all()
    return StreamingResponse(
        BytesIO(export_excel(invoices)),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=invoices.xlsx"},
    )
