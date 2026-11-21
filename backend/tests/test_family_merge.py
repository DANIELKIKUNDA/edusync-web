"""Owner, 2026-11-21: « Regrouper les frères et sœurs » — families with the same responsible and phone are proposed,
the school confirms, children and guardians join the main family; the others are kept as history. No amount changes."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_migration_keeps_merged_families_and_is_provisioned():
    mig = (ROOT / 'backend/migrations/0118_family_merge.sql').read_text(encoding='utf-8')
    assert "merged_into_family_id uuid REFERENCES families(id)" in mig and "DELETE FROM" not in mig.upper()
    assert (ROOT / 'backend/migrations/rollback/0118_family_merge.sql').exists()
    assert '("0118_family_merge", "0118_family_merge.sql")' in (ROOT / 'backend/scripts/provision_database.py').read_text(encoding='utf-8')


def test_merge_moves_children_and_never_touches_money():
    src = (ROOT / 'backend/src/edusync/adapters/postgres_schooling.py').read_text(encoding='utf-8')
    body = src.split("def merge_families(", 1)[1].split("    def get_family(", 1)[0]
    assert "UPDATE students SET family_id=:t" in body and "merged_into_family_id=:t" in body
    assert "finance_" not in body and "DELETE FROM" not in body.upper()
    assert '"f.merged_into_family_id IS NULL"' in src                       # merged families leave the directory


def test_routes_need_the_right_and_whole_school_scope():
    src = (ROOT / 'backend/src/edusync/modules/schooling/api/router.py').read_text(encoding='utf-8')
    assert src.index("@router.get('/families/merge/suggestions')") < src.index("@router.get('/families/{family_id}')")
    body = src.split("def merge_families(", 1)[1]
    assert "_need_whole_school(actor,'families.update')" in body and "action='FAMILY_MERGED'" in body and "reason=body.reason.strip()" in body


def test_ui_and_ci():
    ui = (ROOT / 'frontend/src/schooling.tsx').read_text(encoding='utf-8')
    assert "can('families.update')&&<FamilyMergeSuggestions" in ui and "<AddFamilyToThis" in ui
    assert "tools/ci/family_merge_postgres_integration.py" in (ROOT / '.github/workflows/ci.yml').read_text(encoding='utf-8')
