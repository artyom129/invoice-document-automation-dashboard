from __future__ import annotations

import hashlib
from io import BytesIO
import re

import pandas as pd
from openpyxl.styles import Font, PatternFill
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Invoice

EXPORT_COLUMNS = [
    "id", "filename", "vendor", "invoice_number", "invoice_date", "due_date",
    "currency", "subtotal", "tax", "total", "confidence", "status",
    "is_duplicate", "duplicate_of_id", "issues", "created_at",
]
COLUMN_WIDTHS = {
    "id": 8, "filename": 30, "vendor": 28, "invoice_number": 18, "invoice_date": 14, "due_date": 14,
    "currency": 10, "subtotal": 12, "tax": 10, "total": 12, "confidence": 12, "status": 12,
    "is_duplicate": 12, "duplicate_of_id": 16, "issues": 50, "created_at": 22,
}
MONEY_COLUMNS = ("subtotal", "tax", "total")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_key(value: str | None) -> str:
    """Compare vendors and invoice numbers without caring about case, spacing or dots."""
    return re.sub(r"[\s.,]+", " ", (value or "").lower()).strip()


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def find_duplicate(db: Session, *, vendor: str | None, invoice_number: str | None) -> Invoice | None:
    """The earliest invoice from the same vendor with the same number, if any.

    Rejected invoices do not count: a reviewer who threw one away should be able
    to upload a corrected copy without it being flagged.
    """
    vendor_key = normalize_key(vendor)
    number_key = normalize_key(invoice_number)
    if not vendor_key or not number_key:
        return None
    candidates = db.scalars(
        select(Invoice)
        .where(Invoice.status != "rejected", Invoice.is_duplicate.is_(False))
        .where(func.lower(Invoice.invoice_number) == (invoice_number or "").strip().lower())
        .order_by(Invoice.id)
    ).all()
    for candidate in candidates:
        if normalize_key(candidate.vendor) == vendor_key and normalize_key(candidate.invoice_number) == number_key:
            return candidate
    return None


def spreadsheet_safe(value):
    """Keep text that starts like a formula from running when the file is opened.

    Vendor names and numbers come out of PDFs we did not write, so a vendor
    called ``=HYPERLINK(...)`` would otherwise become a live formula.
    """
    if isinstance(value, str) and value[:1] in {"=", "+", "-", "@", "\t", "\r"}:
        return "'" + value
    return value


def invoice_rows(invoices: list[Invoice]) -> list[dict]:
    return [
        {
            "id": inv.id,
            "filename": spreadsheet_safe(inv.filename),
            "vendor": spreadsheet_safe(inv.vendor),
            "invoice_number": spreadsheet_safe(inv.invoice_number),
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
            "issues": spreadsheet_safe("; ".join(inv.issues)),
            "created_at": inv.created_at.isoformat() if inv.created_at else "",
        }
        for inv in invoices
    ]


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
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="1F2937")
        for index, name in enumerate(EXPORT_COLUMNS, start=1):
            letter = ws.cell(row=1, column=index).column_letter
            ws.column_dimensions[letter].width = COLUMN_WIDTHS[name]
            if name in MONEY_COLUMNS:
                for row in range(2, ws.max_row + 1):
                    ws.cell(row=row, column=index).number_format = "#,##0.00"
    return output.getvalue()
