from app.extractor import extract_invoice_fields

def test_extract_standard_invoice():
    text = """
    Northstar Cloud Services
    Invoice Number: INV-2026-1048
    Invoice Date: 2026-07-22
    Due Date: 2026-08-21
    Subtotal: $1280.00
    Tax: $102.40
    Total: $1382.40
    Currency: USD
    """
    data = extract_invoice_fields(text)
    assert data["vendor"] == "Northstar Cloud Services"
    assert data["invoice_number"] == "INV-2026-1048"
    assert data["invoice_date"] == "2026-07-22"
    assert data["due_date"] == "2026-08-21"
    assert data["subtotal"] == 1280.00
    assert data["tax"] == 102.40
    assert data["total"] == 1382.40
    assert data["currency"] == "USD"
    assert data["confidence"] >= 80

def test_extract_partial_invoice_requires_review():
    data = extract_invoice_fields("Harbor Maintenance Co.\nInvoice Number: HM-5521\nTotal: $410.00")
    assert data["invoice_number"] == "HM-5521"
    assert data["total"] == 410.00
    assert data["confidence"] < 80
