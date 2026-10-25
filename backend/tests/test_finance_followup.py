"""Suivi financier d'un frais (owner 2026-10-25): « en ordre avec mars » = every month up to March settled (cumulative)."""
from __future__ import annotations

from datetime import date
from io import BytesIO

import pytest
from openpyxl import load_workbook

from edusync.modules.finance_recovery.application.documents import followup_pdf, followup_xlsx
from edusync.modules.finance_recovery.domain.followup import class_followup, default_column, fee_groups

MONTHS = ["Septembre", "Octobre", "Novembre", "Décembre", "Janvier", "Février", "Mars", "Avril"]
DUE = [date(2026, 9, 1), date(2026, 10, 1), date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1), date(2027, 2, 1), date(2027, 3, 1), date(2027, 4, 1)]
COLS = [{"key": f"MONTH:{i + 1}:{m}", "group": "MONTHLY", "parent": "Frais mensuels", "label": m, "order": i + 1, "regulatory": False} for i, m in enumerate(MONTHS)]
COLS.append({"key": "FEE:ETAT:1:1re tranche", "group": "FEE", "parent": "Frais de l’État", "label": "1re tranche", "order": 1, "regulatory": True})


def pupil(sid, name, paid_months, terminal_from=None, advance_month=None):
    cells = {}
    for i, m in enumerate(MONTHS):
        cell = {"net": "15000", "paid": "15000" if i < paid_months else "0", "advance": "0", "due_date": DUE[i], "label": m}
        if advance_month is not None and i == advance_month:
            cell["advance"] = "15000"
        if terminal_from is not None and i >= terminal_from:
            cell["status_label"] = "Abandon"
        cells[f"MONTH:{i + 1}:{m}"] = cell
    cells["FEE:ETAT:1:1re tranche"] = {"net": "12000", "paid": "12000", "advance": "0", "due_date": DUE[0], "label": "1re tranche"}
    return {"student_id": sid, "matricule": f"M{sid}", "student_name": name, "cells": cells}


REG = {"class_label": "2e CG", "currency": "CDF", "columns": COLS, "students": [
    pupil("1", "AMANI", 7), pupil("2", "BAHATI", 5), pupil("3", "CIZA", 0), pupil("4", "DUNIA", 3, terminal_from=3), pupil("5", "ESPOIR", 6, advance_month=6)]}


def test_cumulative_march_lists_who_must_be_sent_home():
    d = class_followup(REG, "MONTH:7:Mars", cumulative=True)
    by = {r["student_name"]: r for r in d["rows"]}
    assert d["periods"] == MONTHS[:7] and d["title"] == "Frais mensuels — jusqu’à Mars"
    assert by["AMANI"]["status"] == "OK" and by["ESPOIR"]["status"] == "OK"                 # March covered by an allocated advance
    assert by["BAHATI"]["status"] == "PARTIAL" and by["BAHATI"]["missing"] == ["Février", "Mars"] and by["BAHATI"]["remaining"] == "30000"
    assert by["CIZA"]["status"] == "NONE" and by["CIZA"]["remaining"] == "105000"
    assert by["DUNIA"]["status"] == "OK"                                                      # nothing owed after the abandon
    assert d["counts"] == {"students": 5, "in_order": 3, "not_in_order": 2, "partial": 1}
    assert [r["student_name"] for r in d["rows"]][:2] == ["BAHATI", "CIZA"]                  # pupils not in order first


def test_strict_reading_and_other_fees():
    d = class_followup(REG, "MONTH:7:Mars", cumulative=False)
    assert d["periods"] == ["Mars"] and {r["student_name"] for r in d["rows"] if r["status"] == "NONE"} == {"BAHATI", "CIZA"}
    assert class_followup(REG, "FEE:ETAT:1:1re tranche")["counts"]["in_order"] == 5
    assert [g["label"] for g in fee_groups(COLS)] == ["Frais mensuels", "Frais de l’État"]
    with pytest.raises(LookupError):
        class_followup(REG, "MONTH:99:Inconnu")


def test_default_period_is_the_month_currently_due():
    assert default_column(REG, date(2027, 3, 15)) == "MONTH:7:Mars"
    assert default_column(REG, date(2026, 8, 1)) == "MONTH:1:Septembre"


def test_printable_list_and_excel():
    d = class_followup(REG, "MONTH:7:Mars")
    assert followup_pdf(school={"name": "École"}, year_label="2026-2027", data=d).startswith(b"%PDF")
    ws = load_workbook(BytesIO(followup_xlsx(school={"name": "École"}, year_label="2026-2027", data=d))).active
    assert [c.value for c in ws[6]][:4] == [1, "M2", "BAHATI", "Partiel"] and ws.cell(6, 7).value == 30000.0
