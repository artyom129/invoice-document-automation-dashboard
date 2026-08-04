from pathlib import Path
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from app.database import Base, SessionLocal, engine
from app.extractor import extract_invoice_fields, extract_pdf_text
from app.models import Invoice
from app.services import find_duplicate, sha256_file

BASE_DIR = Path(__file__).resolve().parent
SAMPLES = BASE_DIR / "sample_invoices"
UPLOADS = BASE_DIR / "data" / "uploads"
SAMPLES.mkdir(exist_ok=True)
UPLOADS.mkdir(parents=True, exist_ok=True)

INVOICES = [
    {
        "filename": "northstar_cloud_invoice.pdf",
        "vendor": "Northstar Cloud Services",
        "invoice_number": "INV-2026-1048",
        "invoice_date": "2026-07-22",
        "due_date": "2026-08-21",
        "subtotal": 1280.00,
        "tax": 102.40,
        "total": 1382.40,
        "currency": "USD",
    },
    {
        "filename": "brightline_office_invoice.pdf",
        "vendor": "Brightline Office Supply",
        "invoice_number": "BOS-88721",
        "invoice_date": "2026-07-27",
        "due_date": "2026-08-11",
        "subtotal": 642.50,
        "tax": 51.40,
        "total": 693.90,
        "currency": "USD",
    },
    {
        "filename": "atlas_logistics_invoice.pdf",
        "vendor": "Atlas Logistics Group",
        "invoice_number": "ALG-44019",
        "invoice_date": "2026-07-30",
        "due_date": "2026-08-14",
        "subtotal": 2310.00,
        "tax": 184.80,
        "total": 2494.80,
        "currency": "USD",
    },
    {
        "filename": "vertex_media_invoice.pdf",
        "vendor": "Vertex Media Studio",
        "invoice_number": "VM-260731",
        "invoice_date": "2026-07-31",
        "due_date": "2026-08-15",
        "subtotal": 875.00,
        "tax": 70.00,
        "total": 945.00,
        "currency": "USD",
    },
]

def create_pdf(path: Path, data: dict):
    c = canvas.Canvas(str(path), pagesize=LETTER)
    width, height = LETTER
    c.setFont("Helvetica-Bold", 20)
    c.drawString(54, height - 70, data["vendor"])
    c.setFont("Helvetica-Bold", 28)
    c.drawRightString(width - 54, height - 70, "INVOICE")
    c.setFont("Helvetica", 11)
    y = height - 125
    lines = [
        f"Vendor: {data['vendor']}",
        f"Invoice Number: {data['invoice_number']}",
        f"Invoice Date: {data['invoice_date']}",
        f"Due Date: {data['due_date']}",
        "",
        "Bill To: Example Operations LLC",
        "Description: Professional services and account support",
        "",
        f"Subtotal: ${data['subtotal']:.2f}",
        f"Tax: ${data['tax']:.2f}",
        f"Total: ${data['total']:.2f}",
        f"Currency: {data['currency']}",
    ]
    for line in lines:
        c.drawString(54, y, line)
        y -= 24
    c.save()

def main():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for item in INVOICES:
            sample_path = SAMPLES / item["filename"]
            create_pdf(sample_path, item)
            upload_path = UPLOADS / item["filename"]
            upload_path.write_bytes(sample_path.read_bytes())
            text = extract_pdf_text(upload_path)
            fields = extract_invoice_fields(text)
            file_hash = sha256_file(upload_path)
            duplicate = find_duplicate(
                db,
                file_hash=file_hash,
                vendor=fields.get("vendor"),
                invoice_number=fields.get("invoice_number"),
            )
            invoice = Invoice(
                filename=item["filename"],
                file_hash=file_hash,
                raw_text=text,
                status="approved" if fields["confidence"] >= 80 else "review",
                is_duplicate=bool(duplicate),
                duplicate_of_id=duplicate.id if duplicate else None,
                **fields,
            )
            db.add(invoice)
            db.commit()

        # A deliberately lower-confidence record for the review queue.
        review_pdf = SAMPLES / "harbor_maintenance_partial.pdf"
        c = canvas.Canvas(str(review_pdf), pagesize=LETTER)
        c.setFont("Helvetica-Bold", 20)
        c.drawString(54, 720, "Harbor Maintenance Co.")
        c.setFont("Helvetica", 11)
        c.drawString(54, 670, "Invoice Number: HM-5521")
        c.drawString(54, 640, "Total: $410.00")
        c.save()
        upload_path = UPLOADS / review_pdf.name
        upload_path.write_bytes(review_pdf.read_bytes())
        text = extract_pdf_text(upload_path)
        fields = extract_invoice_fields(text)
        db.add(Invoice(
            filename=review_pdf.name,
            file_hash=sha256_file(upload_path),
            raw_text=text,
            status="review",
            **fields,
        ))
        db.commit()
    finally:
        db.close()
    print("Demo database and sample invoice PDFs created.")

if __name__ == "__main__":
    main()
