from datetime import datetime
from io import BytesIO

from pypdf import PdfReader
from reportlab.lib.pagesizes import A4, A5
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth

from edusync.modules.finance_checkout.application.receipts import money, receipt_pdf


def _receipt():
    return {
        "receipt_number": "REC-2026-000123",
        "amount": "120000",
        "currency": "CDF",
        "created_at": datetime(2026, 10, 25, 9, 42),
        "cashier": "Caissier réel",
        "last_name": "KIKUNDA",
        "middle_name": "NGWEJ",
        "first_name": "Daniel",
        "gender": "M",
        "matricule": "EDU-001",
        "class_label": "2e CG",
        "academic_year": "2026-2027",
        "payment_mode": "CASH",
        "family_name": "Foyer Kikunda",
        "lines": [
            {"fee_label": "Frais scolaires", "period_label": "Octobre", "period_value": "10/2026", "amount": "70000"},
            {"fee_label": "Frais d'inscription", "period_label": "Inscription", "period_value": "2026-2027", "amount": "50000"},
        ],
        "copy_no": 1,
    }


def test_official_receipt_matches_desktop_documentary_blocks_and_real_cashier():
    pdf = PdfReader(BytesIO(receipt_pdf(school={"name": "École de démonstration"}, receipts=[_receipt()], fmt="80MM")))
    assert len(pdf.pages) == 1
    assert 79 < float(pdf.pages[0].mediabox.width) / 2.83464567 < 81
    text = pdf.pages[0].extract_text()
    for label in ("REÇU N°", "ANNÉE SCOLAIRE", "REÇU DE PAIEMENT", "CODE ÉLÈVE",
                  "DÉTAIL DES PAIEMENTS", "Frais scolaires", "Frais / période",
                  "Octobre", "70 000 FC", "TOTAL PAYÉ", "MONTANT EN LETTRES",
                  "MODE DE PAIEMENT", "CAISSIER", "CACHET DE L’ÉCOLE"):
        assert label in text
    assert "Caissier réel" in text
    assert "Foyer Kikunda" in text
    assert "25/10/2026" in text
    assert "120 000 FC" in text
    assert money("50000", "CDF") == "50 000 FC"


def test_receipt_copies_and_formats_keep_one_numbered_receipt_per_page():
    receipt = _receipt()
    for fmt in ("58MM", "80MM", "A5", "A4"):
        pdf = PdfReader(BytesIO(receipt_pdf(school={"name": "École"}, receipts=[receipt], fmt=fmt, copies=2)))
        assert len(pdf.pages) == 2
        assert "Copie 1/2" in pdf.pages[0].extract_text()
        assert "Copie 2/2" in pdf.pages[1].extract_text()
        assert "REC-2026-000123" in pdf.pages[0].extract_text()
        assert "REC-2026-000123" in pdf.pages[1].extract_text()


def test_thermal_ticket_uses_readable_fonts_and_full_text_inside_printable_area():
    receipt = _receipt()
    receipt["payment_reference"] = "REFERENCE" * 14
    receipt["lines"][0]["fee_label"] = "Frais scolaires et cotisation exceptionnelle pour les activités scientifiques"
    receipt["advance_amount"] = "10000"
    receipt["advance_target"] = "Tranche trois"
    receipt["copy_no"] = 2
    school = {"name": "Complexe scolaire international de démonstration à Lubumbashi",
              "address": "Avenue des Écoles numéro 123 commune de démonstration",
              "email": "recette@ecole.example"}
    pdf = PdfReader(BytesIO(receipt_pdf(school=school, receipts=[receipt], fmt="80MM")))
    assert pdf.root_object["/ViewerPreferences"]["/PrintScaling"] == "/None"
    page = pdf.pages[0]
    width, height = float(page.mediabox.width), float(page.mediabox.height)
    sizes = []

    def measure(text, _cm, tm, font, size):
        label = text.strip()
        if not label or not font:
            return
        sizes.append(size)
        assert tm[4] >= 5 * mm - .1
        assert tm[4] + stringWidth(label, font["/BaseFont"][1:], size) <= width - 5 * mm + .1
        assert 5 * mm <= tm[5] < height - 4 * mm

    text = page.extract_text(visitor_text=measure)
    assert min(sizes) >= 9.5 and max(sizes) == 15
    assert "…" not in text
    assert receipt["payment_reference"] in "".join(text.split())
    assert "Avance conservée" in text and "Tranche trois" in text
    assert "DUPLICATA n° 1" in text
    assert "120 000 FC" in text


def test_office_receipts_have_native_a4_and_legacy_a5_dimensions():
    for fmt, size in (("A4", A4), ("A5", A5)):
        page = PdfReader(BytesIO(receipt_pdf(school={"name": "École"}, receipts=[_receipt()], fmt=fmt))).pages[0]
        assert abs(float(page.mediabox.width) - size[0]) < .01
        assert abs(float(page.mediabox.height) - size[1]) < .01
        text = page.extract_text()
        assert "TYPE DE FRAIS" in text and "MONTANT (FC)" in text
        assert "REC-2026-000123" in text and "120 000 FC" in text
