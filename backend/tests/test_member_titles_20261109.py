"""Titles in the feminine / with the sections (owner, 2026-11-09). Words only — the rights never depend on them."""
from pathlib import Path

from edusync.modules.access.domain.titles import role_title, section_phrase

ROOT = Path(__file__).resolve().parents[2]
STD = "SCHOOL_STANDARD"


def test_feminine_titles():
    assert role_title("PROMOTEUR", STD, "Promoteur", "MME") == "Promotrice"
    assert role_title("PREFET_ETUDES", STD, "Préfet des études", "MME") == "Préfète des études"
    assert role_title("CAISSIER", STD, "Caissier", "MME") == "Caissière"
    assert role_title("GESTIONNAIRE", STD, "Gestionnaire", "MME") == "Gestionnaire"          # epicene
    assert role_title("PROMOTEUR", STD, "Promoteur", None) == "Promoteur"                    # not stated: unchanged


def test_section_directions_separate_or_merged():
    assert role_title("DIRECTION_SECTION", STD, "Directeur / Directrice de section", "MME", [("MATERNELLE", "Maternelle")]) == "Directrice de la maternelle"
    assert role_title("DIRECTION_SECTION", STD, "x", "M", [("PRIMAIRE", "Primaire")]) == "Directeur du primaire"
    assert role_title("DIRECTION_SECTION", STD, "x", "MME", [("PRIMAIRE", "Primaire"), ("MATERNELLE", "Maternelle")]) == "Directrice de la maternelle et du primaire"
    assert role_title("DIRECTION_SECTION", STD, "x", None, [("PRIMAIRE", "Primaire")]) == "Direction du primaire"
    assert section_phrase([("MAT", "Maternelle")]) == "de la maternelle"                    # school code ≠ word: the label decides


def test_school_roles_keep_their_own_name():
    assert role_title("ASSISTANT_PROMOTEUR", "SCHOOL_CUSTOM", "Assistant du promoteur", "MME") == "Assistant du promoteur"


def test_wiring():
    router = (ROOT / "backend/src/edusync/modules/access/api/router.py").read_text(encoding="utf-8")
    assert '"role_label": " · ".join(dict.fromkeys(titles))' in router and "civility" in router
    mig = (ROOT / "backend/migrations/0112_membership_civility.sql").read_text(encoding="utf-8")
    assert "ADD COLUMN IF NOT EXISTS civility" in mig and "('M','MME')" in mig
    assert (ROOT / "backend/migrations/rollback/0112_membership_civility.sql").exists()
