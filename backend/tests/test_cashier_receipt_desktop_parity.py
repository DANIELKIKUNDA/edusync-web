from datetime import datetime
from io import BytesIO

from pypdf import PdfReader

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
                  "DÉTAIL DES PAIEMENTS", "TYPE DE FRAIS", "LIBELLÉ / MOIS",
                  "PÉRIODE", "MONTANT (FC)", "TOTAL PAYÉ", "MONTANT EN LETTRES",
                  "MODE DE PAIEMENT", "CAISSIER", "CACHET DE L’ÉCOLE"):
        assert label in text
    assert "Caissier réel" in text
    assert "Foyer Kikunda" in text
    assert "25/10/2026" in text
    assert "120 000 FC" in text
    assert money("50000", "CDF") == "50 000 FC"


def test_receipt_copies_and_formats_keep_one_numbered_receipt_per_page():
    receipt = _receipt()
    for fmt in ("58MM", "80MM", "A5"):
        pdf = PdfReader(BytesIO(receipt_pdf(school={"name": "École"}, receipts=[receipt], fmt=fmt, copies=2)))
        assert len(pdf.pages) == 2
        assert "Copie 1/2" in pdf.pages[0].extract_text()
        assert "Copie 2/2" in pdf.pages[1].extract_text()
        assert "REC-2026-000123" in pdf.pages[0].extract_text()
        assert "REC-2026-000123" in pdf.pages[1].extract_text()
