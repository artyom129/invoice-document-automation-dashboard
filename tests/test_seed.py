import pytest
from sqlalchemy import select

import seed_demo
from app.config import Settings
from app.database import build_engine, build_session_factory
from app.models import Invoice


@pytest.fixture()
def seeded_env(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'seed.db'}")
    monkeypatch.setenv("UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(seed_demo, "SAMPLES", tmp_path / "samples")  # keep the tracked sample PDFs untouched
    return tmp_path


def run_seed(monkeypatch, *args):
    monkeypatch.setattr("sys.argv", ["seed_demo.py", *args])
    seed_demo.main()


def read_statuses():
    settings = Settings.from_env()
    with build_session_factory(build_engine(settings.database_url))() as db:
        return {row.filename: row for row in db.scalars(select(Invoice)).all()}


def test_demo_data_shows_every_outcome(seeded_env, monkeypatch):
    run_seed(monkeypatch)
    invoices = read_statuses()

    assert len(invoices) == len(seed_demo.DEMO)
    assert {name: inv.status for name, inv in invoices.items()} == {
        "northstar_cloud_invoice.pdf": "approved",
        "brightline_office_invoice.pdf": "approved",
        "atlas_logistics_invoice.pdf": "approved",
        "vertex_media_invoice.pdf": "approved",
        "bergmann_elektro_invoice.pdf": "approved",
        "harbor_maintenance_partial.pdf": "review",
        "meridian_print_invoice.pdf": "review",
        "calloway_freight_invoice.pdf": "review",
        "northstar_cloud_invoice_resent.pdf": "duplicate",
        "scanned_receipt.pdf": "review",
    }


def test_european_invoice_is_read_correctly(seeded_env, monkeypatch):
    run_seed(monkeypatch)
    bergmann = read_statuses()["bergmann_elektro_invoice.pdf"]

    assert (bergmann.currency, bergmann.subtotal, bergmann.tax, bergmann.total) == ("EUR", 2150.0, 408.5, 2558.5)
    assert bergmann.invoice_date == "2026-07-22"


def test_each_review_case_explains_itself(seeded_env, monkeypatch):
    run_seed(monkeypatch)
    invoices = read_statuses()

    assert any("Subtotal plus tax" in issue for issue in invoices["meridian_print_invoice.pdf"].issues)
    assert any("two ways" in issue for issue in invoices["calloway_freight_invoice.pdf"].issues)
    assert invoices["scanned_receipt.pdf"].issues[0].startswith("No text found")
    assert invoices["northstar_cloud_invoice_resent.pdf"].duplicate_of_id == invoices["northstar_cloud_invoice.pdf"].id


def test_seeding_does_not_wipe_existing_data_without_reset(seeded_env, monkeypatch):
    run_seed(monkeypatch)

    with pytest.raises(SystemExit) as stopped:
        run_seed(monkeypatch)
    assert "--reset" in str(stopped.value)
    assert len(read_statuses()) == len(seed_demo.DEMO)

    run_seed(monkeypatch, "--reset")
    assert len(read_statuses()) == len(seed_demo.DEMO)


def test_sample_pdfs_are_byte_for_byte_reproducible():
    name, lines = seed_demo.DEMO["northstar_cloud_invoice.pdf"]

    assert seed_demo.pdf_bytes(name, lines) == seed_demo.pdf_bytes(name, lines)
