"""V2 lot 3c — comfort (owner, 2026-11-22: « qu'est-ce que tu peux encore ajouter pour avoir encore plus de facilité ? »).
tools/ci/pedagogy_grades_postgres_integration.py proves the routes over real HTTP + PostgreSQL (sheet PDF, who has not
finished, reminders manual and automatic, group conduct report)."""
import io
from pathlib import Path

from pypdf import PdfReader

from edusync.modules.pedagogy.application.documents import grade_sheet_pdf
from edusync.modules.pedagogy.application.followup import COLUMN, REMIND_DAYS_BEFORE_END

ROOT = Path(__file__).resolve().parents[2]


def test_printable_sheet_lists_present_pupils_only_with_standard_characters():
    pupils = [{"name": "KABILA Jean", "status": "NOTE", "value": 14, "departed": False},
              {"name": "MBUYI Anne", "status": "ABSENT", "value": None, "departed": False},
              {"name": "PARTI Paul", "status": None, "value": None, "departed": True}]
    empty = grade_sheet_pdf(school={"name": "École Test"}, year_label="2026-2027", class_label="1re A", course_label="Numération",
                            period_label="2e période", maximum=20, pupils=pupils, with_marks=False)
    text = "".join(p.extract_text() for p in PdfReader(io.BytesIO(empty)).pages)
    assert empty[:5] == b"%PDF-" and "Fiche de cotation" in text and "KABILA Jean" in text and "PARTI Paul" not in text
    assert "14" not in text.split("KABILA Jean")[1][:6]                                      # an empty sheet stays empty
    full = grade_sheet_pdf(school={"name": "École Test"}, year_label="2026-2027", class_label="1re A", course_label="Numération",
                           period_label="2e période", maximum=20, pupils=pupils, with_marks=True)
    ftext = "".join(p.extract_text() for p in PdfReader(io.BytesIO(full)).pages)
    assert "14" in ftext and "Abs." in ftext and " " not in ftext and " " not in ftext


def test_reminders_and_offline_sheets_wiring():
    assert REMIND_DAYS_BEFORE_END == 3 and set(COLUMN) == {"P1", "P2", "EX1", "P3", "P4", "EX2", "P5", "P6", "EX3"}
    sup = (ROOT / "backend/src/edusync/modules/alerts/application/supervision.py").read_text(encoding="utf-8")
    assert "automatic_reminders(conn, sid)" in sup and "module_code='ACADEMIC'" in sup        # only schools with the module
    followup = (ROOT / "backend/src/edusync/modules/pedagogy/application/followup.py").read_text(encoding="utf-8")
    assert "created_at > now() - interval '1 day'" in followup                               # never twice the same day
    cache = (ROOT / "frontend/src/pedagogy_cache.ts").read_text(encoding="utf-8")
    assert "s.scope === outboxScope()" in cache and "token" not in cache.split("type Store")[1].split("}")[0]
    outbox = (ROOT / "frontend/src/offline/outbox.ts").read_text(encoding="utf-8")
    assert "pedagogy\\/conduct\\/facts\\/batch" in outbox
    conduct = (ROOT / "backend/src/edusync/modules/pedagogy/api/conduct_facts.py").read_text(encoding="utf-8")
    assert "rien n’a été enregistré" in conduct                                              # group report: all or nothing
