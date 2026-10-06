from pathlib import Path
APP=Path('../frontend/src/App.tsx').read_text(encoding='utf-8')
PAGE=Path('../frontend/src/personnel.tsx').read_text(encoding='utf-8')
CSS=Path('../frontend/src/styles.css').read_text(encoding='utf-8')
API=Path('../frontend/src/api.ts').read_text(encoding='utf-8')

def test_personnel_is_real_navigation_target():
    # Closure 2026-10: navigation icons are SVG keys, no emoji.
    assert "['users','Personnel','personnel']" in APP
    assert '<PersonnelPage' in APP

def test_personnel_ui_has_centered_kpis_and_professional_tabs():
    for term in ['personMetrics','metricIcon','metricNumber','Vue d’ensemble','Annuaire','Fonctions & affectations','Historique']:
        assert term in PAGE or term in CSS

def test_personnel_ui_has_real_svg_icon_system_not_emoji_only_cards():
    assert '<svg className="uiIcon"' in PAGE
    assert '.metricIcon' in CSS and 'place-items:center' in CSS

def test_personnel_ui_has_animation_and_reduced_motion_safety():
    assert '@keyframes pageEnter' in CSS
    assert '@keyframes numberPop' in CSS
    assert 'prefers-reduced-motion:reduce' in CSS

def test_personnel_table_prioritizes_register_over_form():
    assert 'personTable' in PAGE and 'staffModal' in PAGE
    assert '.personRow' in CSS

def test_pdf_and_excel_are_permission_gated():
    assert "can('personnel.directory.print_pdf')" in PAGE
    assert "can('personnel.directory.export_xlsx')" in PAGE
    assert 'personnelRegisterPdf' in API and 'personnelRegisterXlsx' in API

def test_profile_has_assignments_children_history_and_pdf():
    for term in ["'assignments'","'children'","'history'",'staffProfilePdf']:
        assert term in PAGE

def test_personnel_ui_exposes_edit_and_audited_status_lifecycle():
    text=PAGE
    assert "updateStaff(" in text
    assert "changeStaffStatus(" in text
    assert "Suspendre" in text and "Réactiver activité" in text


def test_personnel_ui_can_end_an_assignment_without_deleting_history():
    text=PAGE
    assert "endStaffAssignment(" in text
    assert "Motif de fin d’affectation" in text
