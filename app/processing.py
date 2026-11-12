"""Turn an uploaded PDF into an invoice record. Used by the web upload and the demo seeder."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .config import Settings
from .extractor import PdfError, extract_invoice_fields, extract_pdf_text
from .models import Invoice
from .services import find_duplicate, sha256_bytes

NO_TEXT_ISSUE = "No text found in the PDF. It may be a scan, and OCR is not supported."


@dataclass(slots=True)
class Outcome:
    filename: str
    result: str  # "processed", "already_uploaded" or "skipped"
    detail: str
    invoice: Invoice | None = None


def stored_path(settings: Settings, file_hash: str) -> Path:
    """Files are stored under their SHA-256, so the same file is never kept twice."""
    return settings.upload_dir / f"{file_hash}.pdf"


def process_upload(db: Session, settings: Settings, filename: str, data: bytes) -> Outcome:
    filename = (filename or "upload.pdf").strip() or "upload.pdf"

    if not filename.lower().endswith(".pdf"):
        return Outcome(filename, "skipped", "Not a PDF file.")
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes / (1024 * 1024)
        return Outcome(filename, "skipped", f"Larger than the {limit_mb:g} MB limit.")
    if not data.startswith(b"%PDF-"):
        return Outcome(filename, "skipped", "The file is not a valid PDF.")

    file_hash = sha256_bytes(data)
    existing = db.scalar(select(Invoice).where(Invoice.file_hash == file_hash))
    if existing is not None:
        return Outcome(filename, "already_uploaded", f"Same file as invoice #{existing.id} ({existing.filename}).", existing)

    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    path = stored_path(settings, file_hash)
    path.write_bytes(data)

    try:
        text = extract_pdf_text(path)
    except PdfError as exc:
        path.unlink(missing_ok=True)
        return Outcome(filename, "skipped", str(exc))

    if text:
        fields = extract_invoice_fields(text)
    else:
        fields = {key: None for key in ("vendor", "invoice_number", "invoice_date", "due_date", "currency", "subtotal", "tax", "total")}
        fields.update(confidence=0.0, issues=[NO_TEXT_ISSUE])

    issues = list(fields["issues"])
    duplicate = find_duplicate(db, vendor=fields["vendor"], invoice_number=fields["invoice_number"])
    if duplicate is not None:
        issues.insert(0, f"Same vendor and invoice number as invoice #{duplicate.id}.")
        status = "duplicate"
    elif fields["confidence"] >= settings.auto_approve_threshold:
        status = "approved"
    else:
        status = "review"

    invoice = Invoice(
        filename=filename,
        file_hash=file_hash,
        vendor=fields["vendor"],
        invoice_number=fields["invoice_number"],
        invoice_date=fields["invoice_date"],
        due_date=fields["due_date"],
        currency=fields["currency"],
        subtotal=fields["subtotal"],
        tax=fields["tax"],
        total=fields["total"],
        confidence=fields["confidence"],
        status=status,
        is_duplicate=duplicate is not None,
        duplicate_of_id=duplicate.id if duplicate else None,
        raw_text=text,
    )
    invoice.issues = issues
    db.add(invoice)
    try:
        db.commit()
    except IntegrityError:
        # Two uploads of the same file raced each other; the other one won.
        db.rollback()
        return Outcome(filename, "already_uploaded", "Same file as one that was just uploaded.")
    return Outcome(filename, "processed", status, invoice)
