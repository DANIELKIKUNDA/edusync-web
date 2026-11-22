"""V2 lot 1 — official MINEDUC referential (owner, 2026-11-22). Rules on the repository files, without a database;
tools/ci/pedagogy_referential_postgres_integration.py proves them over real HTTP + PostgreSQL."""
import copy
from pathlib import Path

import pytest

from edusync.modules.pedagogy.domain.referential import (CURRENT_VERSION, ReferentialError, check_line, exam_is_double, load,
                                                         suggest_official_class, totals, validate)

ROOT = Path(__file__).resolve().parents[2]
REF = load()


def test_counts_of_the_official_referential():
    assert REF.version == CURRENT_VERSION == "MINEDUC-2024-2025-V2"
    assert (len(REF.sections), len(REF.options), len(REF.classes), len(REF.courses), len(REF.programmes), REF.line_count) == (3, 51, 215, 485, 130, 2658)
    groups = {g: sum(1 for o in REF.options if o["group"] == g) for g in ("GENERAL", "GROUPE_1", "GROUPE_2")}
    assert groups == {"GENERAL": 9, "GROUPE_1": 13, "GROUPE_2": 29}
    assert {o["sigle"]: o["code"] for o in REF.options}["CG"] == 301          # Commerciale et Gestion: technical, group 1
    assert next(o for o in REF.options if o["sigle"] == "CG")["group"] == "GROUPE_1"


def test_humanities_class_codes_are_level_plus_sigle():
    sigle = {o["code"]: o["sigle"] for o in REF.options}
    for c in REF.classes:
        if c["cycle"] == "HUMANITE":
            assert c["code"][0] in "1234" and c["code"] == c["code"][0] + sigle[c["option"]], c   # 1SC, 4CG…


def test_owner_rule_exam_is_twice_the_period_everywhere_and_corrections_applied():
    for p in REF.programmes:
        for line in p["lines"]:
            if line["exam"]:
                assert exam_is_double(line["max"]), (p["class"], line["course"], line["max"])
    line = lambda cls, course: next(l for p in REF.programmes if p["class"] == cls for l in p["lines"] if l["course"] == course)  # noqa: E731
    assert line("2HYDRO", "FRANCAIS")["max"][2] == 100 and line("2HYDRO", "MATHEMATIQUES")["max"][2] == 100
    assert line("3SC", "SYSTEMATIQUE_ET_JARDIN")["max"][2:6:3] == [40, 40] and line("3SC", "GEOLOGIE_ECOLOGIE")["max"][2:6:3] == [40, 40]
    doc = (ROOT / "backend/src/edusync/modules/pedagogy/reference/MINEDUC-2024-2025-V2/CORRECTIONS.md").read_text(encoding="utf-8")
    assert "l'examen est toujours le double de la période" in doc and "4HR" in doc


def test_line_rules_refuse_inconsistent_weighting():
    ok = {"course": "X", "exam": True, "max": [10, 10, 20, 10, 10, 20, 0, 0, 0]}
    check_line("1SC", "SEMESTRIEL", ok)
    with pytest.raises(ReferentialError, match="double"):
        check_line("1SC", "SEMESTRIEL", {**ok, "max": [10, 10, 10, 10, 10, 20, 0, 0, 0]})
    with pytest.raises(ReferentialError, match="semestrielle"):
        check_line("1SC", "SEMESTRIEL", {**ok, "max": [10, 10, 20, 10, 10, 20, 10, 10, 20]})
    with pytest.raises(ReferentialError, match="sans examen"):
        check_line("1SC", "SEMESTRIEL", {**ok, "exam": False})
    check_line("1PR", "TRIMESTRIEL", {**ok, "max": [10, 10, 20, 10, 10, 20, 10, 10, 20]})


def test_validation_refuses_unknown_course_or_duplicate():
    broken = copy.deepcopy(REF)
    broken.programmes[0]["lines"][1]["course"] = broken.programmes[0]["lines"][0]["course"]
    with pytest.raises(ReferentialError, match="double"):
        validate(broken)


def test_suggestions_never_invent_an_official_class():
    sigles = {o["sigle"] for o in REF.options}
    assert suggest_official_class("P1", None, sigles) == "1PR" and suggest_official_class("S8", None, sigles) == "8EB"
    assert suggest_official_class("M3", None, sigles) == "3MAT"
    assert suggest_official_class("H1", "CG", sigles) == "1CG" and suggest_official_class("H4", "hp", sigles) == "4HP"
    assert suggest_official_class("H2", "ELECTRONIQUE", sigles) == "2EI" and suggest_official_class("H3", "CONSTRUCTION", sigles) == "3CONS"
    assert suggest_official_class("H3", "LITTERAIRE", sigles) is None and suggest_official_class("H1", None, sigles) is None
    assert suggest_official_class(None, "CG", sigles) is None


def test_totals_of_a_programme():
    lines = [{"calculable": True, **dict(zip(("max_p1", "max_p2", "max_ex1", "max_p3", "max_p4", "max_ex2", "max_p5", "max_p6", "max_ex3"), l["max"]))}
             for p in REF.programmes if p["class"] == "1SC" for l in p["lines"]]
    assert totals(lines)["max_p1"] == 360 and totals(lines)["max_ex1"] == 720


def test_migration_provisioning_and_routes():
    sql = (ROOT / "backend/migrations/0124_pedagogy_referential.sql").read_text(encoding="utf-8")
    assert "ref_line_exam_is_double" in sql and "max_ex1 = 2*max_p1" in sql and "ref_line_semester" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql and "pedagogy_class_links" in sql
    assert "DROP TABLE" not in sql.upper() and "DELETE FROM" not in sql.upper()
    assert (ROOT / "backend/migrations/rollback/0124_pedagogy_referential.sql").exists()
    prov = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")
    assert '("0124_pedagogy_referential", "0124_pedagogy_referential.sql")' in prov and "load_referential(conn)" in prov
    api = (ROOT / "backend/src/edusync/modules/pedagogy/api/router.py").read_text(encoding="utf-8")
    assert api.count("Depends(require_pedagogy)") == 6 and api.count("Depends(require_school_actor)") == 6
    assert 'text(f"' not in api


def test_v1_setup_assistant_offers_exactly_the_official_options():
    """Owner 2026-11-22: « tu peux le corriger » — the V1 assistant lists the 51 official options (same file)."""
    import re
    src = (ROOT / "frontend/src/settings_wizards.tsx").read_text(encoding="utf-8")
    front = {(m[0], m[2], int(m[3])) for m in re.findall(r"\{code:'([^']+)',label:'([^']+)',group:'(GENERAL|GROUPE_1|GROUPE_2)',official:(\d+)\}", src)
             for m in [(m[0], m[1], m[2], m[3])]}
    assert front == {(o["sigle"], o["group"], o["code"]) for o in REF.options}
    assert "LITTERAIRE" not in src.split("export const RDC_OPTIONS")[1].split("];")[0]


def test_no_double_encoded_label_anywhere():
    """The source had 27 labels like « PÃ©dagogie » (repaired at build time, noted in CORRECTIONS.md)."""
    folder = ROOT / "backend/src/edusync/modules/pedagogy/reference/MINEDUC-2024-2025-V2"
    for f in list(folder.glob("*.json")) + [ROOT / "frontend/src/settings_wizards.tsx"]:
        text = f.read_text(encoding="utf-8")
        assert "Ã" not in text and "Â" not in text, f.name
    assert {o["sigle"]: o["label"] for o in REF.options}["HP"] == "Pédagogie Générale"
