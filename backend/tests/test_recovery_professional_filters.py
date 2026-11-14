from io import BytesIO
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from edusync.modules.finance_recovery.application.documents import (
    class_register_bundle_pdf,
    class_register_bundle_xlsx,
)


ROOT = Path(__file__).resolve().parents[2]


def _register(label: str):
    return {
        "class_label": label,
        "currency": "CDF",
        "columns": [{"key": "REGISTRATION", "group": "REGISTRATION", "parent": "", "label": "Inscription"}],
        "students": [{"student_id": label, "student_name": "Élève Test", "matricule": "M1", "enrolled_on": "2026-09-01", "cells": {}}],
        "footer": {"debtors": 0, "expected": 0, "regularized": 0, "remaining": 0, "in_order": 0, "not_in_order": 0, "recovery_rate": 0},
    }


def test_ui_uses_section_then_class_and_fee_then_period():
    source = (ROOT / "frontend/src/recovery.tsx").read_text(encoding="utf-8")
    assert "filteredClasses" in source
    assert "Section du registre" in source
    assert "Type de frais" in source
    assert "Mois de synthèse" in source
    assert "recoveryClassRegisterBundleExport" in source


def test_api_filters_real_fees_instead_of_using_synthetic_order_one_hundred():
    router = (ROOT / "backend/src/edusync/modules/finance_recovery/api/router.py").read_text(encoding="utf-8")
    repository = (ROOT / "backend/src/edusync/adapters/postgres_finance_recovery.py").read_text(encoding="utf-8")
    assert "@router.get('/fees')" in router
    assert "period_order:int|None=Query(None,ge=1,le=12)" in router
    assert "fc.fee_type_id=%s" in repository
    assert "fc.period_order=%s" in repository


def test_grouped_register_exports_contain_every_class():
    registers = [_register("1re A"), _register("1re B")]
    school = {"name": "École Test"}
    workbook = load_workbook(BytesIO(class_register_bundle_xlsx(school=school, year_label="2026-2027", registers=registers)))
    assert workbook.sheetnames == ["1re A", "1re B"]
    pdf = PdfReader(BytesIO(class_register_bundle_pdf(school=school, year_label="2026-2027", registers=registers)))
    assert len(pdf.pages) == 2
