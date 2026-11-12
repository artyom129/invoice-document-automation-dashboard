"""Read invoice fields out of PDF text with plain rules, and say how sure we are.

Nothing here guesses silently. Every field that is missing, ambiguous, or does
not add up is reported in ``issues`` so a person can check it against the PDF.
"""
from __future__ import annotations

from datetime import date
import re
from pathlib import Path
from typing import Any

import fitz

# One amount: digits with optional thousands and decimal separators. Spaces
# inside a number are allowed, but only ordinary or non-breaking spaces, so the
# match never runs across a line break into the next line's number.
AMOUNT = r"(\d[\d.,   ]*\d|\d)(?!\s*%)"
LABEL_GAP = r"[^\n\d]*?"

KNOWN_CURRENCIES = ("USD", "EUR", "GBP", "CAD", "AUD", "CHF", "JPY", "CNY", "INR", "KZT", "RUB", "PLN", "SEK", "NOK", "DKK")
SYMBOL_CURRENCIES = {"$": "USD", "€": "EUR", "£": "GBP"}

WEIGHTS = {
    "vendor": 15,
    "invoice_number": 20,
    "invoice_date": 10,
    "due_date": 5,
    "currency": 10,
    "subtotal": 10,
    "tax": 10,
    "total": 20,
}
LABELS = {
    "vendor": "Vendor",
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "due_date": "Due date",
    "currency": "Currency",
    "subtotal": "Subtotal",
    "tax": "Tax",
    "total": "Total",
}
MISMATCH_PENALTY = 30
DATE_ORDER_PENALTY = 10
# A date that is printed but cannot be read is worse than a missing one: someone
# has to look at the PDF, so the invoice must not be approved automatically.
UNREADABLE_DATE_PENALTY = 20

MONTHS = {
    name: number
    for number, names in enumerate(
        [
            ("january", "jan"), ("february", "feb"), ("march", "mar"), ("april", "apr"),
            ("may",), ("june", "jun"), ("july", "jul"), ("august", "aug"),
            ("september", "sep", "sept"), ("october", "oct"), ("november", "nov"), ("december", "dec"),
        ],
        start=1,
    )
    for name in names
}


class PdfError(Exception):
    """The file could not be opened as a PDF."""


def extract_pdf_text(path: Path) -> str:
    try:
        with fitz.open(path) as doc:
            return "\n".join(page.get_text("text") for page in doc).strip()
    except Exception as exc:  # PyMuPDF raises several error types for damaged files
        raise PdfError(f"Could not read the PDF ({exc})") from exc


# --------------------------------------------------------------------------
# Amounts and dates
# --------------------------------------------------------------------------

def parse_amount(raw: str | None) -> float | None:
    """Turn '1,234.56', '1.234,56', '1 234,56' or '410' into a float."""
    if raw is None:
        return None
    text = re.sub(r"[   ]", "", raw.strip())
    if not text or not re.fullmatch(r"-?[\d.,]+", text):
        return None

    if "," in text and "." in text:
        decimal = "," if text.rfind(",") > text.rfind(".") else "."
    elif "," in text:
        decimal = "," if re.fullmatch(r"-?\d+,\d{1,2}", text) else None
    elif "." in text:
        decimal = "." if re.fullmatch(r"-?\d+\.\d{1,2}", text) else None
    else:
        decimal = None

    if decimal == ",":
        text = text.replace(".", "").replace(",", ".")
    elif decimal == ".":
        text = text.replace(",", "")
    else:
        text = text.replace(",", "").replace(".", "")
    try:
        return round(float(text), 2)
    except ValueError:
        return None


def _valid_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def parse_date(raw: str | None) -> tuple[str | None, bool]:
    """Return ``(iso_date, ambiguous)``.

    ``2026-07-22``, ``22.07.2026`` and ``July 22, 2026`` are unambiguous.
    ``03/04/2026`` could be March 4 or April 3, so it comes back as
    ``(None, True)`` instead of a guess. ``07/22/2026`` is clearly month-first.
    """
    if not raw:
        return None, False
    text = raw.strip()

    match = re.search(r"\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b", text)
    if match:
        return _valid_date(int(match[1]), int(match[2]), int(match[3])), False

    match = re.search(r"\b(\d{1,2})([-/.])(\d{1,2})\2(\d{4})\b", text)
    if match:
        first, separator, second, year = int(match[1]), match[2], int(match[3]), int(match[4])
        if separator == ".":
            return _valid_date(year, second, first), False  # 22.07.2026 is day first
        if first > 12:
            return _valid_date(year, second, first), False
        if second > 12:
            return _valid_date(year, first, second), False
        if first == second:
            return _valid_date(year, first, second), False
        return None, True

    match = re.search(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", text)
    if match and match[1].lower() in MONTHS:
        return _valid_date(int(match[3]), MONTHS[match[1].lower()], int(match[2])), False

    match = re.search(r"\b(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})\b", text)
    if match and match[2].lower() in MONTHS:
        return _valid_date(int(match[3]), MONTHS[match[2].lower()], int(match[1])), False

    return None, False


# --------------------------------------------------------------------------
# Field finders
# --------------------------------------------------------------------------

def _first(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip(" :-\t")
    return None


def _amount(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if match:
            value = parse_amount(match.group(1))
            if value is not None:
                return value
    return None


def _guess_vendor(text: str) -> str | None:
    for line in [x.strip() for x in text.splitlines() if x.strip()]:
        lower = line.lower()
        if any(token in lower for token in ["invoice", "bill to", "date", "total", "tax", "page "]):
            continue
        if len(line) <= 80 and re.search(r"[A-Za-z]", line):
            return line
    return None


def _find_date(labels: str, text: str) -> tuple[str | None, str | None, bool]:
    """Return ``(iso, raw, ambiguous)`` for the first line that follows ``labels``."""
    match = re.search(rf"(?:{labels})\s*[:\-]\s*([^\n\r]+)", text, re.IGNORECASE)
    if not match:
        return None, None, False
    raw = match.group(1).strip()
    iso, ambiguous = parse_date(raw)
    return iso, raw, ambiguous


def _find_currency(text: str) -> str | None:
    explicit = re.search(r"currency\s*[:\-]\s*([A-Za-z]{3})\b", text, re.IGNORECASE)
    if explicit and explicit.group(1).upper() in KNOWN_CURRENCIES:
        return explicit.group(1).upper()
    for code in KNOWN_CURRENCIES:
        if re.search(rf"\b{code}\b", text):
            return code
    for symbol, code in SYMBOL_CURRENCIES.items():
        if symbol in text:
            return code
    return None


def extract_invoice_fields(text: str) -> dict[str, Any]:
    invoice_number = _first(
        [
            r"(?:invoice|inv)\s*(?:number|no\.?|num\.?|#)\s*[:\-#]?\s*((?=[A-Z0-9\-/_.]*\d)[A-Z0-9][A-Z0-9\-/_.]*)",
            r"\b((?=[A-Z0-9\-]*\d)INV[-\s]?[A-Z0-9\-]+)\b",
        ],
        text,
    )
    if invoice_number:
        invoice_number = invoice_number.rstrip(".")

    invoice_date, invoice_raw, invoice_ambiguous = _find_date(
        r"invoice\s+date|issue\s+date|date\s+of\s+issue|(?<!due )date", text
    )
    due_date, due_raw, due_ambiguous = _find_date(r"due\s+date|payment\s+due|due\s+on", text)

    vendor = _first([r"(?:vendor|supplier|from)\s*[:\-]\s*([^\n\r]+)"], text) or _guess_vendor(text)

    subtotal = _amount(
        [rf"^\s*(?:sub[\s\-]?total|net\s+amount){LABEL_GAP}{AMOUNT}"],
        text,
    )
    tax = _amount(
        [
            rf"^\s*(?:sales\s+tax|tax|vat|gst)\b(?!\s*(?:id|no|number|reg|registration|code)\b){LABEL_GAP}"
            rf"(?:\(?\d+(?:[.,]\d+)?\s*%\)?{LABEL_GAP})?{AMOUNT}"
        ],
        text,
    )
    total = _amount(
        [
            rf"^\s*(?:grand\s+total|invoice\s+total|total\s+amount|total\s+due|amount\s+due|balance\s+due){LABEL_GAP}{AMOUNT}",
            rf"^\s*total\b(?!\s+(?:tax|vat|gst|discount|before))\s*{LABEL_GAP}{AMOUNT}",
        ],
        text,
    )

    fields: dict[str, Any] = {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "currency": _find_currency(text),
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }

    issues: list[str] = []
    unreadable_dates = 0
    for key, label in LABELS.items():
        if fields[key] is not None:
            continue
        if key == "invoice_date" and invoice_raw:
            unreadable_dates += 1
            issues.append(
                f"Invoice date “{invoice_raw}” could be read two ways. Check the PDF."
                if invoice_ambiguous
                else f"Could not read the invoice date “{invoice_raw}”."
            )
        elif key == "due_date" and due_raw:
            unreadable_dates += 1
            issues.append(
                f"Due date “{due_raw}” could be read two ways. Check the PDF."
                if due_ambiguous
                else f"Could not read the due date “{due_raw}”."
            )
        else:
            issues.append(f"{label} not found.")

    confidence = sum(WEIGHTS[key] for key, value in fields.items() if value is not None)

    if unreadable_dates:
        confidence -= UNREADABLE_DATE_PENALTY

    if subtotal is not None and tax is not None and total is not None:
        expected = round(subtotal + tax, 2)
        if abs(expected - total) > 0.01:
            issues.append(f"Subtotal plus tax is {expected:.2f}, but the total is {total:.2f}.")
            confidence -= MISMATCH_PENALTY

    if invoice_date and due_date and due_date < invoice_date:
        issues.append("The due date is before the invoice date.")
        confidence -= DATE_ORDER_PENALTY

    fields["confidence"] = float(max(0, min(100, confidence)))
    fields["issues"] = issues
    return fields
