from __future__ import annotations

import re
from pathlib import Path
from typing import Any
import fitz

MONEY = r"([0-9][0-9,\s]*\.\d{2})"

def extract_pdf_text(path: Path) -> str:
    chunks: list[str] = []
    with fitz.open(path) as doc:
        for page in doc:
            chunks.append(page.get_text("text"))
    return "\n".join(chunks).strip()

def _first(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return match.group(1).strip(" :-\t")
    return None

def _money(patterns: list[str], text: str) -> float | None:
    value = _first(patterns, text)
    if value is None:
        return None
    try:
        return float(value.replace(",", "").replace(" ", ""))
    except ValueError:
        return None

def _guess_vendor(text: str) -> str | None:
    for line in [x.strip() for x in text.splitlines() if x.strip()]:
        lower = line.lower()
        if any(token in lower for token in ["invoice", "bill to", "date:", "total:", "tax:"]):
            continue
        if len(line) <= 80 and not re.fullmatch(r"[\d\W]+", line):
            return line
    return None

def extract_invoice_fields(text: str) -> dict[str, Any]:
    invoice_number = _first([
        r"(?:invoice\s*(?:number|no\.?|#)|inv\s*#)\s*[:\-]?\s*([A-Z0-9\-\/]+)",
        r"\b(INV[-\s]?[A-Z0-9\-]+)\b",
    ], text)

    invoice_date = _first([
        r"(?:invoice\s+date|date)\s*[:\-]\s*([0-9]{1,4}[\/\-.][0-9]{1,2}[\/\-.][0-9]{1,4})",
        r"(?:invoice\s+date|date)\s*[:\-]\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    ], text)

    due_date = _first([
        r"(?:due\s+date|payment\s+due)\s*[:\-]\s*([0-9]{1,4}[\/\-.][0-9]{1,2}[\/\-.][0-9]{1,4})",
        r"(?:due\s+date|payment\s+due)\s*[:\-]\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})",
    ], text)

    vendor = _first([
        r"(?:vendor|supplier|from)\s*[:\-]\s*([^\n\r]+)",
    ], text) or _guess_vendor(text)

    subtotal = _money([
        rf"(?:subtotal|sub total)\s*[:$€£ ]+\s*{MONEY}",
    ], text)

    tax = _money([
        rf"(?:tax|vat|gst)\s*[:$€£ ]+\s*{MONEY}",
    ], text)

    total = _money([
        rf"(?m)^\s*(?:grand\s+total|amount\s+due|invoice\s+total|total)\s*[:$€£ ]+\s*{MONEY}\s*$",
    ], text)

    currency = None
    if "$" in text or re.search(r"\bUSD\b", text, re.I):
        currency = "USD"
    elif "€" in text or re.search(r"\bEUR\b", text, re.I):
        currency = "EUR"
    elif "£" in text or re.search(r"\bGBP\b", text, re.I):
        currency = "GBP"

    fields = {
        "vendor": vendor,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "currency": currency,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
    }

    weighted = {
        "vendor": 15,
        "invoice_number": 20,
        "invoice_date": 10,
        "due_date": 5,
        "currency": 10,
        "subtotal": 10,
        "tax": 10,
        "total": 20,
    }
    confidence = sum(weighted[k] for k, v in fields.items() if v is not None)
    fields["confidence"] = float(confidence)
    return fields
