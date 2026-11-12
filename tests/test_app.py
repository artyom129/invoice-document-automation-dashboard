import io

from openpyxl import load_workbook

from conftest import invoice_pdf, text_pdf, upload, upload_one


def api(client, query=""):
    return client.get(f"/api/invoices{query}").json()


def result_rows(response):
    """The outcome words shown in the upload result table, in order."""
    return [word for word in ("approved", "needs review", "duplicate", "already uploaded", "skipped") for _ in range(response.text.count(f"status-{word.replace(' ', '')}"))]


# --------------------------------------------------------------------------
# Pages and health
# --------------------------------------------------------------------------

def test_health_checks_the_database(client):
    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["database"] == "ok"


def test_pages_render_when_empty(client):
    dashboard = client.get("/")
    assert dashboard.status_code == 200
    assert "No invoices yet" in dashboard.text
    assert client.get("/upload").status_code == 200
    assert client.get("/docs").status_code == 200


def test_browser_gets_an_error_page_and_api_clients_get_json(client):
    html = client.get("/invoices/999", headers={"Accept": "text/html"})
    assert html.status_code == 404
    assert "Invoice not found." in html.text
    assert "Back to the invoice queue" in html.text

    assert client.get("/invoices/999").json() == {"detail": "Invoice not found."}
    assert client.get("/api/invoices/999").status_code == 404


# --------------------------------------------------------------------------
# Uploading
# --------------------------------------------------------------------------

def test_complete_invoice_is_extracted_and_approved(client):
    response = upload(client, ("acme.pdf", invoice_pdf()))

    assert response.status_code == 200
    assert "1 processed, 1 approved" in response.text
    [invoice] = api(client)
    assert invoice["status"] == "approved"
    assert invoice["vendor"] == "Acme Supplies"
    assert invoice["invoice_number"] == "A-100"
    assert (invoice["subtotal"], invoice["tax"], invoice["total"]) == (100.0, 8.0, 108.0)
    assert invoice["confidence"] == 100.0
    assert invoice["issues"] == []


def test_incomplete_invoice_waits_for_review_with_reasons(client):
    upload(client, ("partial.pdf", text_pdf("Invoice Number: HM-1", "Total: $410.00", vendor="Harbor Co.")))

    [invoice] = api(client)
    assert invoice["status"] == "review"
    assert invoice["confidence"] < 80
    assert "Invoice date not found." in invoice["issues"]


def test_totals_that_do_not_add_up_go_to_review_even_if_every_field_is_present(client):
    upload(client, ("odd.pdf", invoice_pdf(subtotal="500.00", tax="40.00", total="560.00")))

    [invoice] = api(client)
    assert invoice["status"] == "review"
    assert any("Subtotal plus tax" in issue for issue in invoice["issues"])


def test_several_files_in_one_batch_each_get_an_outcome(client):
    response = upload(
        client,
        ("a.pdf", invoice_pdf(number="A-1")),
        ("b.pdf", invoice_pdf(vendor="Other Ltd", number="B-1")),
        ("c.pdf", text_pdf("Total: $5.00", vendor="Third")),
    )

    assert "3 processed, 2 approved, 1 need review" in response.text
    assert len(api(client)) == 3


def test_same_vendor_and_number_is_flagged_as_a_duplicate(client):
    first_id = upload_one(client, "first.pdf", invoice_pdf())
    response = upload(client, ("second.pdf", invoice_pdf(total="108.00", tax="8.00") + b"\n% resent"))

    assert "1 duplicate" in response.text
    second = next(item for item in api(client) if item["filename"] == "second.pdf")
    assert second["status"] == "duplicate"
    assert second["is_duplicate"] is True
    assert second["duplicate_of_id"] == first_id
    assert second["issues"][0] == f"Same vendor and invoice number as invoice #{first_id}."


def test_duplicate_match_ignores_case_and_punctuation(client):
    upload(client, ("first.pdf", invoice_pdf(vendor="Acme Supplies Inc.", number="inv-7")))
    upload(client, ("second.pdf", invoice_pdf(vendor="ACME  SUPPLIES INC", number="INV-7") + b"\n% copy"))

    assert {item["filename"]: item["status"] for item in api(client)}["second.pdf"] == "duplicate"


def test_underscore_in_an_invoice_number_is_not_a_wildcard(client):
    upload(client, ("first.pdf", invoice_pdf(number="INV_1")))
    upload(client, ("second.pdf", invoice_pdf(number="INVX1")))

    assert {item["filename"]: item["status"] for item in api(client)}["second.pdf"] == "approved"


def test_a_rejected_invoice_does_not_block_a_corrected_copy(client):
    first_id = upload_one(client, "first.pdf", invoice_pdf())
    client.post(f"/invoices/{first_id}/reject")
    upload(client, ("fixed.pdf", invoice_pdf(total="108.00") + b"\n% fixed"))

    assert {item["filename"]: item["status"] for item in api(client)}["fixed.pdf"] == "approved"


def test_uploading_the_same_file_twice_reports_it(client):
    data = invoice_pdf()
    upload(client, ("acme.pdf", data))
    response = upload(client, ("renamed.pdf", data))

    assert "1 already uploaded" in response.text
    assert "Same file as invoice #1" in response.text
    assert len(api(client)) == 1


def test_files_that_are_not_pdfs_are_skipped_with_a_reason(client):
    response = upload(
        client,
        ("notes.txt", b"hello"),
        ("fake.pdf", b"this is not a pdf"),
        ("empty.pdf", b""),
        content_type="application/octet-stream",
    )

    assert response.status_code == 200
    assert "3 skipped" in response.text
    assert "Not a PDF file." in response.text
    assert "The file is not a valid PDF." in response.text
    assert api(client) == []


def test_a_damaged_pdf_does_not_break_the_batch(client):
    # PyMuPDF repairs what it can, so this opens as a page-less file with no text.
    damaged = b"%PDF-1.4\n1 0 obj\n<< /Broken >>\ngarbage garbage\n"
    response = upload(client, ("damaged.pdf", damaged), ("good.pdf", invoice_pdf()))

    assert response.status_code == 200
    by_name = {item["filename"]: item for item in api(client)}
    assert by_name["good.pdf"]["status"] == "approved"
    assert by_name["damaged.pdf"]["status"] == "review"
    assert by_name["damaged.pdf"]["issues"][0].startswith("No text found")


def test_an_unreadable_pdf_is_skipped_and_leaves_no_file_behind(client, settings, monkeypatch):
    from app import processing
    from app.extractor import PdfError

    def broken(_path):
        raise PdfError("Could not read the PDF (cannot open broken document)")

    monkeypatch.setattr(processing, "extract_pdf_text", broken)
    response = upload(client, ("broken.pdf", invoice_pdf()), ("also.pdf", invoice_pdf(number="B-2")))

    assert "2 skipped" in response.text
    assert "Could not read the PDF" in response.text
    assert api(client) == []
    assert list(settings.upload_dir.glob("*.pdf")) == []


def test_a_pdf_without_text_is_sent_to_review_and_says_why(client):
    upload(client, ("scan.pdf", text_pdf()))

    [invoice] = api(client)
    assert invoice["status"] == "review"
    assert invoice["confidence"] == 0.0
    assert invoice["issues"] == ["No text found in the PDF. It may be a scan, and OCR is not supported."]


def test_files_over_the_size_limit_are_skipped(client, settings):
    settings.max_upload_bytes = 1000
    response = upload(client, ("big.pdf", invoice_pdf() + b"\n%" + b"x" * 5000))

    assert "Larger than the" in response.text
    assert api(client) == []


def test_submitting_without_a_file_gives_a_clear_result(client):
    response = client.post("/upload", files=[("files", ("", b"", "application/octet-stream"))])

    assert response.status_code == 200
    assert "No files were selected." in response.text


def test_pdfs_are_stored_under_their_hash(client, settings):
    upload(client, ("acme.pdf", invoice_pdf()))

    [stored] = list(settings.upload_dir.glob("*.pdf"))
    assert len(stored.stem) == 64


# --------------------------------------------------------------------------
# Reviewing
# --------------------------------------------------------------------------

def test_detail_page_shows_issues_pdf_and_extracted_text(client):
    invoice_id = upload_one(client, "partial.pdf", text_pdf("Invoice Number: HM-1", "Total: $410.00", vendor="Harbor Co."))
    page = client.get(f"/invoices/{invoice_id}")

    assert page.status_code == 200
    assert "What to check" in page.text
    assert "Invoice date not found." in page.text
    assert f"/invoices/{invoice_id}/pdf" in page.text
    assert "HM-1" in page.text


def test_original_pdf_is_served_inline(client):
    data = invoice_pdf()
    invoice_id = upload_one(client, "acme.pdf", data)
    response = client.get(f"/invoices/{invoice_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline")
    assert response.content == data


def test_missing_pdf_file_gives_404_and_the_page_still_works(client, settings):
    invoice_id = upload_one(client, "acme.pdf", invoice_pdf())
    for stored in settings.upload_dir.glob("*.pdf"):
        stored.unlink()

    assert client.get(f"/invoices/{invoice_id}/pdf").status_code == 404
    assert "The original file is not stored." in client.get(f"/invoices/{invoice_id}").text


def test_approve_and_reject(client):
    invoice_id = upload_one(client, "partial.pdf", text_pdf("Total: $5.00", vendor="Harbor Co."))

    assert client.post(f"/invoices/{invoice_id}/approve", follow_redirects=False).status_code == 303
    assert api(client)[0]["status"] == "approved"
    client.post(f"/invoices/{invoice_id}/reject")
    assert api(client)[0]["status"] == "rejected"
    assert client.post("/invoices/999/approve").status_code == 404
    assert client.post("/invoices/999/reject").status_code == 404


def test_approving_a_flagged_duplicate_keeps_both_invoices(client):
    upload(client, ("first.pdf", invoice_pdf()))
    upload(client, ("second.pdf", invoice_pdf() + b"\n% again"))
    duplicate = next(item for item in api(client) if item["status"] == "duplicate")

    client.post(f"/invoices/{duplicate['id']}/approve")

    after = client.get(f"/api/invoices/{duplicate['id']}").json()
    assert after["status"] == "approved"
    assert after["is_duplicate"] is False
    assert after["duplicate_of_id"] is None


def test_editing_fields_normalizes_values(client):
    invoice_id = upload_one(client, "acme.pdf", invoice_pdf())
    response = client.post(
        f"/invoices/{invoice_id}/update",
        data={
            "vendor": "  New Vendor  ", "invoice_number": "N-1", "invoice_date": "22.07.2026", "due_date": "",
            "currency": "eur", "subtotal": "1.000,00", "tax": "190,00", "total": "1.190,00",
            "status": "approved", "notes": " checked ",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    invoice = client.get(f"/api/invoices/{invoice_id}").json()
    assert invoice["vendor"] == "New Vendor"
    assert invoice["invoice_date"] == "2026-07-22"
    assert invoice["due_date"] is None
    assert invoice["currency"] == "EUR"
    assert (invoice["subtotal"], invoice["tax"], invoice["total"]) == (1000.0, 190.0, 1190.0)
    assert invoice["notes"] == "checked"


def test_invalid_edits_are_explained_and_the_input_is_kept(client):
    invoice_id = upload_one(client, "acme.pdf", invoice_pdf())
    response = client.post(
        f"/invoices/{invoice_id}/update",
        data={"vendor": "Typed Vendor", "invoice_date": "last week", "currency": "dollars", "subtotal": "abc", "status": "shipped"},
    )

    assert response.status_code == 400
    page = response.text
    assert "Subtotal “abc” is not a number." in page
    assert "must look like 2026-07-22" in page
    assert "Status must be one of" in page
    assert "three-letter code" in page
    assert 'value="Typed Vendor"' in page  # nothing the user typed is lost
    assert client.get(f"/api/invoices/{invoice_id}").json()["vendor"] == "Acme Supplies"  # and nothing was saved


# --------------------------------------------------------------------------
# Queue, search, API
# --------------------------------------------------------------------------

def fill(client):
    upload(client, ("a.pdf", invoice_pdf(vendor="Alpha Co", number="A-1")))
    upload(client, ("b.pdf", invoice_pdf(vendor="Beta_Co", number="B-2")))
    upload(client, ("c.pdf", text_pdf("Total: $9.00", vendor="Gamma 100% Ltd")))


def test_search_and_status_filters(client):
    fill(client)

    assert [i["vendor"] for i in api(client, "?q=alpha")] == ["Alpha Co"]
    assert [i["vendor"] for i in api(client, "?q=b-2")] == ["Beta_Co"]
    assert [i["filename"] for i in api(client, "?status=review")] == ["c.pdf"]
    assert len(api(client, "?status=approved")) == 2
    assert len(api(client, "?status=nonsense")) == 3  # an unknown status is ignored, not an error


def test_percent_and_underscore_are_searched_literally(client):
    fill(client)

    assert [i["vendor"] for i in api(client, "?q=100%25")] == ["Gamma 100% Ltd"]
    assert [i["vendor"] for i in api(client, "?q=a_x")] == []
    assert [i["vendor"] for i in api(client, "?q=Beta_")] == ["Beta_Co"]
    assert len(api(client, "?q=%25")) == 1


def test_dashboard_lists_invoices_and_paginates(client, settings):
    for number in range(7):
        upload(client, (f"inv{number}.pdf", invoice_pdf(number=f"N-{number}")))

    first = client.get("/")
    assert "Page 1 · 7 invoices" in first.text
    assert "Next" in first.text
    assert "Previous" not in first.text
    second = client.get("/?page=2")
    assert "Previous" in second.text
    assert "Next" not in second.text
    assert second.text.count("data-href") == 2  # 7 invoices, 5 per page
    assert client.get("/?page=0").status_code == 422


def test_dashboard_filters_keep_working(client):
    fill(client)
    page = client.get("/?status=review&q=gamma").text

    assert "Gamma 100% Ltd" in page
    assert "Alpha Co" not in page
    assert "No invoices match these filters." in client.get("/?q=zzz").text


def test_api_limit_offset_and_detail(client):
    fill(client)

    assert len(api(client, "?limit=2")) == 2
    assert len(api(client, "?limit=2&offset=2")) == 1
    assert client.get("/api/invoices?limit=0").status_code == 422
    detail = client.get(f"/api/invoices/{api(client)[0]['id']}").json()
    assert {"issues", "notes", "duplicate_of_id", "confidence"} <= detail.keys()


def test_stats_sum_value_per_currency_and_leave_out_duplicates_and_rejected(client):
    upload(client, ("usd.pdf", invoice_pdf(number="U-1", total="108.00")))
    upload(client, ("usd_dup.pdf", invoice_pdf(number="U-1") + b"\n% dup"))
    upload(client, ("eur.pdf", invoice_pdf(vendor="Euro GmbH", number="E-1", subtotal="200.00", tax="38.00", total="238.00", currency="EUR", symbol="€")))
    rejected_id = upload_one(client, "rej.pdf", invoice_pdf(vendor="Rej Ltd", number="R-1", total="108.00"))
    client.post(f"/invoices/{rejected_id}/reject")

    stats = client.get("/api/stats").json()

    assert stats["total"] == 4
    assert stats["approved"] == 2 and stats["duplicate"] == 1 and stats["rejected"] == 1
    assert stats["value_by_currency"] == [{"currency": "EUR", "total": 238.0}, {"currency": "USD", "total": 108.0}]


def test_dashboard_shows_the_value_for_each_currency_separately(client):
    upload(client, ("usd.pdf", invoice_pdf(number="U-1")))
    upload(client, ("eur.pdf", invoice_pdf(vendor="Euro GmbH", number="E-1", subtotal="200.00", tax="38.00", total="238.00", currency="EUR", symbol="€")))
    page = client.get("/").text

    assert "EUR 238.00" in page
    assert "USD 108.00" in page


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------

def test_csv_export_and_status_filter(client):
    fill(client)
    everything = client.get("/export.csv")
    approved = client.get("/export.csv?status=approved")

    assert everything.status_code == 200
    assert everything.headers["content-disposition"].endswith("invoices.csv")
    assert len(everything.text.strip().splitlines()) == 4
    assert len(approved.text.strip().splitlines()) == 3
    assert everything.text.startswith("﻿id,filename,vendor")  # BOM, so Excel reads UTF-8


def test_excel_export_has_a_styled_header_and_money_formats(client):
    fill(client)
    sheet = load_workbook(io.BytesIO(client.get("/export.xlsx").content))["Invoices"]
    headers = [cell.value for cell in sheet[1]]

    assert headers[:3] == ["id", "filename", "vendor"]
    assert sheet.max_row == 4
    assert sheet.freeze_panes == "A2"
    assert sheet["A1"].font.bold is True
    total_column = headers.index("total") + 1
    assert sheet.cell(row=2, column=total_column).number_format == "#,##0.00"


def test_exports_work_without_invoices(client):
    assert client.get("/export.csv").text.lstrip("﻿").startswith("id,filename")
    assert load_workbook(io.BytesIO(client.get("/export.xlsx").content))["Invoices"].max_row == 1


def test_issues_are_exported(client):
    upload(client, ("odd.pdf", invoice_pdf(subtotal="500.00", tax="40.00", total="560.00")))

    assert "Subtotal plus tax is 540.00" in client.get("/export.csv").text


def test_formulas_in_pdf_text_are_neutralized_in_exports(client):
    invoice_id = upload_one(client, "evil.pdf", invoice_pdf())
    client.post(
        f"/invoices/{invoice_id}/update",
        data={"vendor": '=HYPERLINK("http://evil.test","pay")', "invoice_number": "+1+1", "status": "approved"},
    )

    assert "'=HYPERLINK" in client.get("/export.csv").text
    sheet = load_workbook(io.BytesIO(client.get("/export.xlsx").content))["Invoices"]
    assert sheet.cell(row=2, column=3).value.startswith("'=")
    assert sheet.cell(row=2, column=3).data_type == "s"
    assert sheet.cell(row=2, column=4).value == "'+1+1"
