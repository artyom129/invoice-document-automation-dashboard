import pytest

from app.extractor import extract_invoice_fields, parse_amount, parse_date


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
    assert data["issues"] == []


def test_extract_partial_invoice_requires_review():
    data = extract_invoice_fields("Harbor Maintenance Co.\nInvoice Number: HM-5521\nTotal: $410.00")
    assert data["invoice_number"] == "HM-5521"
    assert data["total"] == 410.00
    assert data["confidence"] < 80
    assert "Invoice date not found." in data["issues"]
    assert "Subtotal not found." in data["issues"]


# --------------------------------------------------------------------------
# Amounts
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("1,234.56", 1234.56),
    ("1.234,56", 1234.56),
    ("1 234,56", 1234.56),
    ("1 234,56", 1234.56),   # narrow no-break space, as some PDFs use
    ("1,234,567.89", 1234567.89),
    ("1.234.567,89", 1234567.89),
    ("12,50", 12.5),
    ("1,234", 1234.0),
    ("410", 410.0),
    ("0.99", 0.99),
])
def test_amounts_in_common_formats(raw, expected):
    assert parse_amount(raw) == expected


@pytest.mark.parametrize("raw", ["", "abc", "12abc", None])
def test_unreadable_amounts_are_none(raw):
    assert parse_amount(raw) is None


@pytest.mark.parametrize("line, expected", [
    ("Total: $410.00", 410.0),
    ("Total (USD): 1,234.50", 1234.5),
    ("Amount Due: $410.00", 410.0),
    ("Balance Due   $99.90", 99.9),
    ("Grand Total: € 2.558,50", 2558.5),
    ("Invoice Total: 75", 75.0),
])
def test_total_label_variants(line, expected):
    assert extract_invoice_fields(line)["total"] == expected


def test_grand_total_wins_over_a_plain_total_line():
    data = extract_invoice_fields("Total: 100.00\nGrand Total: 120.00")

    assert data["total"] == 120.0


def test_total_tax_line_is_not_the_total():
    data = extract_invoice_fields("Total Tax: 10.00\nTotal: 110.00")

    assert data["total"] == 110.0


def test_tax_id_and_tax_rate_are_not_the_tax_amount():
    data = extract_invoice_fields("Tax ID: 123456789\nTax Rate: 8%\nTax: $8.00")

    assert data["tax"] == 8.0


def test_tax_with_a_percentage_in_the_label():
    assert extract_invoice_fields("VAT (19%): € 408,50")["tax"] == 408.5


def test_amounts_do_not_run_across_lines():
    data = extract_invoice_fields("Subtotal: $1280.00\nTax: $102.40\nTotal: $1382.40")

    assert (data["subtotal"], data["tax"], data["total"]) == (1280.0, 102.4, 1382.4)


# --------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("2026-07-22", ("2026-07-22", False)),
    ("2026/07/22", ("2026-07-22", False)),
    ("22.07.2026", ("2026-07-22", False)),
    ("22/07/2026", ("2026-07-22", False)),
    ("07/22/2026", ("2026-07-22", False)),
    ("July 22, 2026", ("2026-07-22", False)),
    ("Jul 22 2026", ("2026-07-22", False)),
    ("22 July 2026", ("2026-07-22", False)),
    ("22nd July, 2026", ("2026-07-22", False)),
    ("05/05/2026", ("2026-05-05", False)),
    ("03/04/2026", (None, True)),      # March 4 or April 3: do not guess
    ("31/02/2026", (None, False)),     # not a real date
    ("soon", (None, False)),
    ("", (None, False)),
])
def test_date_parsing(raw, expected):
    assert parse_date(raw) == expected


def test_ambiguous_date_is_reported_instead_of_guessed():
    data = extract_invoice_fields("Invoice Number: A1\nInvoice Date: 03/04/2026\nTotal: 10.00")

    assert data["invoice_date"] is None
    assert any("two ways" in issue for issue in data["issues"])


def test_a_date_that_cannot_be_read_blocks_automatic_approval():
    complete = (
        "Vendor: X Ltd\nInvoice Number: A1\nInvoice Date: {date}\nDue Date: 2026-08-01\n"
        "Subtotal: 10.00\nTax: 1.00\nTotal: 11.00\nCurrency: USD"
    )

    assert extract_invoice_fields(complete.format(date="2026-07-01"))["confidence"] == 100.0
    assert extract_invoice_fields(complete.format(date="03/04/2026"))["confidence"] < 80
    assert extract_invoice_fields(complete.format(date="whenever"))["confidence"] < 80


def test_unreadable_date_is_reported():
    data = extract_invoice_fields("Invoice Date: next Tuesday")

    assert data["invoice_date"] is None
    assert any("Could not read the invoice date" in issue for issue in data["issues"])


def test_due_date_label_is_not_taken_for_the_invoice_date():
    data = extract_invoice_fields("Due Date: 2026-08-21\nInvoice Date: 2026-07-22")

    assert (data["invoice_date"], data["due_date"]) == ("2026-07-22", "2026-08-21")


def test_plain_date_label_is_used_when_there_is_no_invoice_date():
    assert extract_invoice_fields("Date: 2026-07-22")["invoice_date"] == "2026-07-22"


# --------------------------------------------------------------------------
# Checks that lower the confidence
# --------------------------------------------------------------------------

def test_subtotal_plus_tax_must_match_the_total():
    data = extract_invoice_fields("Vendor: X Ltd\nInvoice Number: A1\nSubtotal: 500.00\nTax: 40.00\nTotal: 560.00")

    assert any("Subtotal plus tax is 540.00, but the total is 560.00" in issue for issue in data["issues"])
    assert data["confidence"] < 80


def test_matching_totals_add_no_issue():
    data = extract_invoice_fields("Subtotal: 500.00\nTax: 40.00\nTotal: 540.00")

    assert not any("Subtotal plus tax" in issue for issue in data["issues"])


def test_one_cent_of_rounding_is_tolerated():
    data = extract_invoice_fields("Subtotal: 10.00\nTax: 0.83\nTotal: 10.84")

    assert not any("Subtotal plus tax" in issue for issue in data["issues"])


def test_due_date_before_invoice_date_is_flagged():
    data = extract_invoice_fields("Invoice Date: 2026-07-22\nDue Date: 2026-06-01")

    assert "The due date is before the invoice date." in data["issues"]


def test_empty_text_gives_zero_confidence():
    data = extract_invoice_fields("")

    assert data["confidence"] == 0.0
    assert len(data["issues"]) == 8


# --------------------------------------------------------------------------
# Other fields
# --------------------------------------------------------------------------

def test_vendor_label_wins_over_the_first_line():
    data = extract_invoice_fields("INVOICE\nSome header\nVendor: Real Vendor Ltd")

    assert data["vendor"] == "Real Vendor Ltd"


def test_invoice_number_must_contain_a_digit():
    data = extract_invoice_fields("Invoice Number:\nInvoice Date: 2026-07-22")

    assert data["invoice_number"] is None


@pytest.mark.parametrize("line, expected", [
    ("Invoice No. 4471", "4471"),
    ("Invoice #: A-77/B", "A-77/B"),
    ("Inv # 90210", "90210"),
    ("Ref INV-2026-5", "INV-2026-5"),
])
def test_invoice_number_variants(line, expected):
    assert extract_invoice_fields(line)["invoice_number"] == expected


@pytest.mark.parametrize("text, expected", [
    ("Currency: EUR\nTotal: $5.00", "EUR"),
    ("Total 10.00 GBP", "GBP"),
    ("Total: € 10,00", "EUR"),
    ("Total: £10.00", "GBP"),
    ("Total: $10.00", "USD"),
    ("Total: 10.00", None),
])
def test_currency_detection(text, expected):
    assert extract_invoice_fields(text)["currency"] == expected
