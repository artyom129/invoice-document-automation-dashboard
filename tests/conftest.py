"""Shared fixtures. Each test gets an in-memory database and its own upload folder."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from seed_demo import pdf_bytes, standard


@pytest.fixture()
def settings(tmp_path) -> Settings:
    return Settings(
        database_url="sqlite://",  # in-memory: creating a file database is slow on some disks
        upload_dir=tmp_path / "uploads",
        page_size=5,
    )


@pytest.fixture()
def client(settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def invoice_pdf(
    vendor="Acme Supplies",
    number="A-100",
    date="2026-07-01",
    due="2026-07-31",
    subtotal="100.00",
    tax="8.00",
    total="108.00",
    **extra,
) -> bytes:
    """A complete, correct invoice unless a field is overridden."""
    name, lines = standard(vendor, number, date, due, subtotal, tax, total, **extra)
    return pdf_bytes(name, lines)


def text_pdf(*lines: str, vendor: str | None = None) -> bytes:
    return pdf_bytes(vendor, list(lines))


def upload(client: TestClient, *files: tuple[str, bytes], content_type: str = "application/pdf"):
    """Post one or more (filename, bytes) files to the upload form."""
    return client.post("/upload", files=[("files", (name, data, content_type)) for name, data in files])


def upload_one(client: TestClient, name: str, data: bytes) -> int:
    """Upload a single file and return the id of the invoice it created."""
    response = upload(client, (name, data))
    assert response.status_code == 200
    invoices = client.get("/api/invoices?limit=500").json()
    return next(item["id"] for item in invoices if item["filename"] == name)
