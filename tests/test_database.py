from sqlalchemy import inspect, text

from app.database import Base, build_engine, ensure_schema
from app.models import Invoice
from app.database import build_session_factory


def test_ensure_schema_creates_tables():
    engine = build_engine("sqlite://")

    assert ensure_schema(engine) == []
    assert "invoices" in inspect(engine).get_table_names()


def test_columns_added_in_newer_versions_are_added_to_an_old_database():
    engine = build_engine("sqlite://")
    with engine.begin() as connection:
        # The table as an earlier version created it: no issues_json column.
        connection.execute(text(
            "CREATE TABLE invoices (id INTEGER PRIMARY KEY, filename VARCHAR(255) NOT NULL, file_hash VARCHAR(64) NOT NULL UNIQUE,"
            " vendor VARCHAR(255), invoice_number VARCHAR(100), invoice_date VARCHAR(50), due_date VARCHAR(50), currency VARCHAR(10),"
            " subtotal FLOAT, tax FLOAT, total FLOAT, confidence FLOAT, status VARCHAR(30), is_duplicate BOOLEAN, duplicate_of_id INTEGER,"
            " raw_text TEXT, notes TEXT, created_at DATETIME, updated_at DATETIME)"
        ))
        connection.execute(text("INSERT INTO invoices (id, filename, file_hash, status) VALUES (1, 'old.pdf', 'abc', 'approved')"))

    assert ensure_schema(engine) == ["invoices.issues_json"]
    assert ensure_schema(engine) == []  # a second run changes nothing

    with build_session_factory(engine)() as session:
        old = session.get(Invoice, 1)
        assert old.filename == "old.pdf"
        assert old.issues == []  # the old row reads as having no issues


def test_issues_round_trip_and_survive_bad_data():
    invoice = Invoice(filename="a.pdf", file_hash="h")

    assert invoice.issues == []
    invoice.issues = ["Total not found.", "Due date “soon” could not be read."]
    assert invoice.issues == ["Total not found.", "Due date “soon” could not be read."]
    invoice.issues_json = "not json"
    assert invoice.issues == []
    invoice.issues_json = '{"a": 1}'
    assert invoice.issues == []


def test_base_knows_the_invoice_table():
    assert "invoices" in Base.metadata.tables
