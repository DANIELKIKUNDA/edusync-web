"""Rapport de recouvrement de direction (owner, 2026-11-14): pure computation, PDF and wiring. No real pupil data."""
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from pypdf import PdfReader

from edusync.modules.finance_recovery.application.direction_report_document import direction_report_pdf
from edusync.modules.finance_recovery.domain.direction_report import build_direction_report, french_date, natural_key

ROOT = Path(__file__).resolve().parents[2]
AS_OF = date(2026, 11, 14)


def charge(eid, cls, sec, net, paid=0, *, fee="Minerval", period="Octobre", advance=0, outside=0, phone="0990000000", name=None):
    return {"enrollment_id": eid, "student_name": name or f"ÉLÈVE {eid}", "matricule": f"M{eid}", "enrolled_on": date(2026, 9, 1),
            "class_id": f"c-{cls}", "class_label": cls, "section_id": f"s-{sec}", "section_label": sec, "fee_label": fee, "period_label": period,
            "net": Decimal(net), "paid": Decimal(paid), "advance": Decimal(advance), "outside": Decimal(outside),
            "contact_name": "Parent" if phone else "", "contact_phone": phone}


def october():
    return [
        charge(1, "1MAT", "Maternelle", 85000, 85000),
        charge(2, "1MAT", "Maternelle", 85000, 0, phone=""),
        charge(3, "2MAT", "Maternelle", 85000, 40000),                 # partiel
        charge(4, "10EB", "Secondaire", 100000, 100000),
        charge(5, "7EB", "Secondaire", 100000, 0, advance=100000),      # avance affectée à octobre : à jour
        charge(6, "7EB", "Secondaire", 100000, 0, outside=30000),       # régularisation hors caisse : partiel
        charge(7, "7EB", "Secondaire", 100000, 150000),                 # jamais plus que le dû
        charge(8, "1MAT", "Maternelle", 0, 0),                          # exonéré : hors calcul
    ]


def test_counts_amounts_and_rate_follow_the_register_rule():
    r = build_direction_report(october(), [], as_of=AS_OF, currency="CDF", fee_label="Minerval", period_label="Octobre")
    t = r["total"]
    assert (t["concerned"], t["in_order"], t["not_in_order"], t["partial"]) == (7, 4, 3, 2)
    assert t["expected"] == Decimal(655000)
    assert t["collected"] == Decimal(85000 + 40000 + 100000 + 100000 + 30000 + 100000)
    assert t["remaining"] == t["expected"] - t["collected"]
    assert t["rate"] == Decimal("69.5")
    assert [s["label"] for s in r["sections"]] == ["Maternelle", "Secondaire"]
    assert [c["label"] for c in r["classes"]] == ["1MAT", "2MAT", "7EB", "10EB"]      # ordre naturel, pas alphabétique
    assert r["title"] == "Minerval — Octobre" and r["scope_label"] == "« Minerval d’octobre »"


def test_analysis_and_unpaid_list_with_contacts():
    r = build_direction_report(october(), [], as_of=AS_OF, currency="CDF", fee_label="Minerval", period_label="Octobre", min_class_size=1)
    a = r["analysis"]
    assert a["full_classes"] == ["10EB"]
    assert a["lowest"][0]["label"] == "2MAT"
    assert a["biggest"][0]["label"] == "1MAT" and a["biggest_sum"] == r["total"]["remaining"]
    assert a["without_contact"] == 1
    assert [u["enrollment_id"] for u in r["unpaid"]] == ["2", "3", "6"]
    assert r["unpaid"][1]["missing"] == ["Octobre (partiel)"]


def test_all_fees_mode_gives_a_per_fee_synthesis_and_named_missing_periods():
    rows = october()[:3] + [charge(1, "1MAT", "Maternelle", 50000, 0, fee="Frais de bus", period="1re tranche")]
    r = build_direction_report(rows, [], as_of=AS_OF, currency="CDF")
    assert [f["label"] for f in r["fees"]] == ["Frais de bus", "Minerval"]
    assert r["fees"][0]["concerned"] == 1 and r["fees"][1]["concerned"] == 3
    first = next(u for u in r["unpaid"] if u["enrollment_id"] == "1")
    assert first["missing"] == ["Frais de bus 1re tranche"]
    assert r["title"] == "Tous les frais échus" and "14 novembre 2026" in r["scope_label"]


def test_not_due_pupils_are_listed_apart_and_never_counted():
    exempt = [{"enrollment_id": 9, "student_name": "TARDIF", "matricule": "M9", "class_label": "7EB", "section_label": "Secondaire",
               "enrolled_on": date(2026, 10, 22), "period_label": "Octobre", "reason": "ARRIVAL"},
              {"enrollment_id": 8, "student_name": "AGENT", "matricule": "M8", "class_label": "1MAT", "section_label": "Maternelle",
               "enrolled_on": date(2026, 9, 1), "period_label": "Octobre", "reason": "EXEMPTION"}]
    r = build_direction_report(october(), exempt, as_of=AS_OF, currency="CDF", fee_label="Minerval", period_label="Octobre")
    assert r["total"]["concerned"] == 7
    assert [g["reason"] for g in r["exempted"]] == ["ARRIVAL", "EXEMPTION"]
    assert r["exempted_counts"] == {"ARRIVAL": 1, "EXEMPTION": 1}


def test_helpers():
    assert french_date(date(2026, 11, 1)) == "1er novembre 2026"
    assert sorted(["10EB", "2MAT", "7EB"], key=natural_key) == ["2MAT", "7EB", "10EB"]


def _text(pdf: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(pdf)).pages)


def test_pdf_is_complete_and_human():
    exempt = [{"enrollment_id": 9, "student_name": "TARDIF & FILS <B>", "matricule": "M9", "class_label": "7EB", "section_label": "Secondaire",
               "enrolled_on": date(2026, 10, 22), "period_label": "Octobre", "reason": "ARRIVAL"}]
    r = build_direction_report(october(), exempt, as_of=AS_OF, currency="CDF", fee_label="Minerval", period_label="Octobre")
    text = _text(direction_report_pdf(school={"name": "École Test"}, year_label="2026-2027", report=r))
    for part in ("Rapport de recouvrement", "Minerval — Octobre", "Synthèse", "Résultats par section", "Résultats par classe", "Analyse",
                 "Annexe 1", "Annexe 2", "Visa de la Direction", "Situation au 14 novembre 2026", "TARDIF & FILS <B>"):
        assert part in text, part
    for word in ("EduSync", "Recommandations", "SQL", "API"):
        assert word not in text


def test_pdf_all_fees_and_empty_scope():
    rows = october()[:3] + [charge(1, "1MAT", "Maternelle", 50000, 0, fee="Frais de bus", period="1re tranche")]
    text = _text(direction_report_pdf(school={"name": "École Test"}, year_label="2026-2027", report=build_direction_report(rows, [], as_of=AS_OF, currency="CDF")))
    assert "Résultats par type de frais" in text and "Non réglé" in text
    empty = build_direction_report([], [], as_of=AS_OF, currency="USD", fee_label="Minerval", period_label="Juin")
    assert "Aucun élève n’est concerné" in _text(direction_report_pdf(school={"name": "École Test"}, year_label="2026-2027", report=empty))


def test_wiring_rights_scope_and_screen():
    router = (ROOT / "backend/src/edusync/modules/finance_recovery/api/router.py").read_text(encoding="utf-8")
    repo = (ROOT / "backend/src/edusync/adapters/postgres_finance_recovery.py").read_text(encoding="utf-8")
    screen = (ROOT / "frontend/src/recovery.tsx").read_text(encoding="utf-8")
    assert "@router.get('/direction-report.pdf')" in router
    assert "need(actor, 'finance.recovery.monthly.read'); need(actor, 'finance.views.vf01.export')" in router
    assert "scopes=actor.scopes_for('finance.recovery.monthly.read')" in router
    assert "fc.due_date<=%s" in repo and "finance_exigibility_assessments" in repo
    panel = (ROOT / "frontend/src/recovery_direction.tsx").read_text(encoding="utf-8")
    assert "Rapport de direction" in screen and "<RecoveryDirection " in screen
    assert "recoveryDirectionReportPdf" in panel and "can('finance.views.vf01.export')" in panel
