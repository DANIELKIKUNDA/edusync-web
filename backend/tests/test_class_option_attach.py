"""Owner, 2026-11-19: a Humanités class opened without its option can be attached to it afterwards (headcounts par option)."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_route_requires_the_class_right_version_and_idempotency():
    src = (ROOT / 'backend/src/edusync/modules/settings/api/router.py').read_text(encoding='utf-8')
    body = src.split("def change_class_option(", 1)[1].split("@router.post('/classes/{class_id}/status')", 1)[0]
    assert "_need(actor,'settings.classes.rename')" in body and '_expected(if_match)' in body and '_key(idempotency_key)' in body
    assert "SCHOOL_CLASS_OPTION_CHANGED" in body


def test_repository_only_accepts_humanities_classes_and_options_of_the_same_section():
    src = (ROOT / 'backend/src/edusync/adapters/postgres_settings.py').read_text(encoding='utf-8')
    body = src.split("def set_class_option(", 1)[1].split("def set_class_status(", 1)[0]
    assert "('H1','H2','H3','H4')" in body
    assert "section_id=:sec AND enabled" in body
    assert "version=:expected" in body
    assert "ARCHIVED" in body


def test_structure_menu_offers_the_options_of_humanities_classes():
    ui = (ROOT / 'frontend/src/settings_structure.tsx').read_text(encoding='utf-8')
    assert "setClassOption(token, c, o?.id ?? null)" in ui
    assert "/^H[1-4]$/i.test(c.reference_code ?? '')" in ui
    assert "Rattacher à {o.label}" in ui and "Retirer l’option" in ui
