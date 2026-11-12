"""Create demo invoices that show every outcome: approved, needs review, duplicate.

    python seed_demo.py            # refuses to touch a database that already has invoices
    python seed_demo.py --reset    # wipes invoices and stored PDFs first
"""
from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
import shutil
import sys

from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas
from sqlalchemy import func, select

from app.config import Settings
from app.database import Base, build_engine, build_session_factory, ensure_schema
from app.models import Invoice
from app.processing import process_upload

BASE_DIR = Path(__file__).resolve().parent
SAMPLES = BASE_DIR / "sample_invoices"


def pdf_bytes(vendor: str | None, lines: list[str]) -> bytes:
    """A one-page invoice. ``invariant=1`` keeps the bytes identical on every run."""
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=LETTER, invariant=1)
    width, height = LETTER
    if vendor:
        c.setFont("Helvetica-Bold", 20)
        c.drawString(54, height - 70, vendor)
        c.setFont("Helvetica-Bold", 26)
        c.drawRightString(width - 54, height - 70, "INVOICE")
    c.setFont("Helvetica", 11)
    y = height - 125
    for line in lines:
        c.drawString(54, y, line)
        y -= 24
    c.save()
    return buffer.getvalue()


def standard(vendor, number, date, due, subtotal, tax, total, currency="USD", symbol="$"):
    return vendor, [
        f"Vendor: {vendor}",
        f"Invoice Number: {number}",
        f"Invoice Date: {date}",
        f"Due Date: {due}",
        "",
        "Bill To: Example Operations LLC",
        "Description: Professional services and account support",
        "",
        f"Subtotal: {symbol}{subtotal}",
        f"Tax: {symbol}{tax}",
        f"Total: {symbol}{total}",
        f"Currency: {currency}",
    ]


DEMO = {
    "northstar_cloud_invoice.pdf": standard("Northstar Cloud Services", "INV-2026-1048", "2026-07-22", "2026-08-21", "1280.00", "102.40", "1382.40"),
    "brightline_office_invoice.pdf": standard("Brightline Office Supply", "BOS-88721", "2026-07-27", "2026-08-11", "642.50", "51.40", "693.90"),
    "atlas_logistics_invoice.pdf": standard("Atlas Logistics Group", "ALG-44019", "2026-07-30", "2026-08-14", "2310.00", "184.80", "2494.80"),
    "vertex_media_invoice.pdf": standard("Vertex Media Studio", "VM-260731", "2026-07-31", "2026-08-15", "875.00", "70.00", "945.00"),
    # European number format and a day-first date: read correctly, and approved.
    "bergmann_elektro_invoice.pdf": (
        "Bergmann Elektro GmbH",
        [
            "Vendor: Bergmann Elektro GmbH",
            "Invoice Number: BE-2026-077",
            "Invoice Date: 22.07.2026",
            "Due Date: 21.08.2026",
            "",
            "Subtotal: € 2.150,00",
            "VAT (19%): € 408,50",
            "Total: € 2.558,50",
        ],
    ),
    # Only some fields are present, so it waits for review.
    "harbor_maintenance_partial.pdf": ("Harbor Maintenance Co.", ["Invoice Number: HM-5521", "Total: $410.00"]),
    # The numbers do not add up: 500.00 + 40.00 is not 560.00.
    "meridian_print_invoice.pdf": standard("Meridian Print Works", "MPW-3310", "2026-07-29", "2026-08-28", "500.00", "40.00", "560.00"),
    # 03/04/2026 could be March 4 or April 3, so the date is left for a person.
    "calloway_freight_invoice.pdf": (
        "Calloway Freight",
        ["Vendor: Calloway Freight", "Invoice Number: CF-1207", "Invoice Date: 03/04/2026", "Due Date: 2026-05-03", "", "Subtotal: $720.00", "Tax: $57.60", "Total: $777.60", "Currency: USD"],
    ),
    # The same vendor and number as the first invoice, sent again as a new file.
    "northstar_cloud_invoice_resent.pdf": (
        "Northstar Cloud Services",
        ["Vendor: Northstar Cloud Services", "Invoice Number: INV-2026-1048", "Invoice Date: 2026-07-22", "Due Date: 2026-08-21", "", "Subtotal: $1280.00", "Tax: $102.40", "Total: $1382.40", "Currency: USD", "", "Reminder: second notice"],
    ),
    # A page with no text layer, like a scan.
    "scanned_receipt.pdf": (None, []),
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Create demo invoices.")
    parser.add_argument("--reset", action="store_true", help="delete existing invoices and stored PDFs first")
    args = parser.parse_args()

    settings = Settings.from_env()
    engine = build_engine(settings.database_url)
    ensure_schema(engine)
    SessionLocal = build_session_factory(engine)

    with SessionLocal() as probe:
        existing = probe.scalar(select(func.count(Invoice.id))) or 0
    if existing and not args.reset:
        sys.exit("The database already contains invoices. Run `python seed_demo.py --reset` to replace them.")

    if args.reset:
        Base.metadata.drop_all(engine)
        ensure_schema(engine)
        if settings.upload_dir.exists():
            shutil.rmtree(settings.upload_dir)

    SAMPLES.mkdir(exist_ok=True)
    with SessionLocal() as db:
        for filename, (vendor, lines) in DEMO.items():
            data = pdf_bytes(vendor, lines)
            (SAMPLES / filename).write_bytes(data)
            outcome = process_upload(db, settings, filename, data)
            print(f"{filename}: {outcome.result} ({outcome.detail})")
    print("Demo invoices created.")


if __name__ == "__main__":
    main()
