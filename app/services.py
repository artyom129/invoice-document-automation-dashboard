from __future__ import annotations

import hashlib
from io import BytesIO
from pathlib import Path
import pandas as pd
from sqlalchemy import or_
from sqlalchemy.orm import Session

from .models import Invoice

EXPORT_COLUMNS = [
    "id", "filename", "vendor", "invoice_number", "invoice_date", "due_date",
    "currency", "subtotal", "tax", "total", "confidence", "status",
    "is_duplicate", "duplicate_of_id", "created_at"
]

def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def find_duplicate(
    db: Session,
    *,
    file_hash: str,
    vendor: str | None,
    invoice_number: str | None,
) -> Invoice | None:
    exact = db.query(Invoice).filter(Invoice.file_hash == file_hash).first()
    if exact:
        return exact
    if vendor and invoice_number:
        return (
            db.query(Invoice)
            .filter(
                Invoice.vendor.ilike(vendor),
                Invoice.invoice_number.ilike(invoice_number),
            )
            .first()
        )
    return None

def invoice_rows(invoices: list[Invoice]) -> list[dict]:
    rows = []
    for inv in invoices:
        rows.append({
            "id": inv.id,
            "filename": inv.filename,
            "vendor": inv.vendor,
            "invoice_number": inv.invoice_number,
            "invoice_date": inv.invoice_date,
            "due_date": inv.due_date,
            "currency": inv.currency,
            "subtotal": inv.subtotal,
            "tax": inv.tax,
            "total": inv.total,
            "confidence": inv.confidence,
            "status": inv.status,
            "is_duplicate": inv.is_duplicate,
            "duplicate_of_id": inv.duplicate_of_id,
            "created_at": inv.created_at.isoformat() if inv.created_at else "",
        })
    return rows

def export_csv(invoices: list[Invoice]) -> bytes:
    df = pd.DataFrame(invoice_rows(invoices), columns=EXPORT_COLUMNS)
    return df.to_csv(index=False).encode("utf-8-sig")

def export_excel(invoices: list[Invoice]) -> bytes:
    df = pd.DataFrame(invoice_rows(invoices), columns=EXPORT_COLUMNS)
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Invoices", index=False)
        ws = writer.book["Invoices"]
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        widths = {
            "A": 8, "B": 30, "C": 28, "D": 18, "E": 15, "F": 15,
            "G": 10, "H": 14, "I": 12, "J": 14, "K": 12, "L": 16,
            "M": 14, "N": 16, "O": 22,
        }
        for col, width in widths.items():
            ws.column_dimensions[col].width = width
    return output.getvalue()
