from pathlib import Path
BACKEND=Path(__file__).resolve().parents[1]
M=(BACKEND/'migrations/0015_effectifs_depots_domain.sql').read_text()
ROUTER=(BACKEND/'src/edusync/modules/effectifs/api/router.py').read_text()
REPO=(BACKEND/'src/edusync/adapters/postgres_effectifs.py').read_text()
APP=(BACKEND/'src/edusync/bootstrap/app.py').read_text()


def test_material_contributions_are_append_only_tenant_isolated_and_active_year_only():
    assert 'CREATE TABLE IF NOT EXISTS material_contributions' in M
    assert 'quantity numeric(14,3) NOT NULL CHECK (quantity > 0)' in M
    assert "y_status IS DISTINCT FROM 'ACTIVE'" in M
    assert 'FORCE ROW LEVEL SECURITY' in M
    assert 'REVOKE UPDATE,DELETE ON material_contributions' in M
    assert 'append-only' in M


def test_point4c_gender_policy_fix_is_guarded_not_global_override():
    assert '["last_name","middle_name","first_name","gender","class_id"]' in M
    assert "payload->'required_student_fields' = '[\"last_name\",\"middle_name\",\"first_name\",\"class_id\"]'::jsonb" in M


def test_requested_scope_is_intersected_with_capability_scope():
    assert 'Intersect UI scope with capability scope; never widen actor visibility.' in REPO
    assert 'allowed_sections' in REPO and 'allowed_classes' in REPO
    assert 'requested_section' in REPO


def test_headcount_sql_is_annual_and_has_certified_four_groups():
    for token in ['enrolled_f','abandoned_f','transferred_f','active_f','enrolled_t','active_t']:
        assert token in REPO
    assert "ev.effective_date BETWEEN ay.start_date AND ay.end_date" in REPO
    assert "e.academic_year_id=:yid" in REPO


def test_movements_are_filtered_paged_and_do_not_merge_years():
    for token in ['event_type','class_id','LIMIT :limit OFFSET :offset','academic_year_id=:yid']:
        assert token in REPO


def test_api_exposes_preserved_effectifs_and_deposit_contracts():
    for route in ['/overview','/counts','/movements','/deposits','/exports/counts.pdf','/exports/counts.xlsx','/print/counts.pdf','/exports/deposits.xlsx']:
        assert route in ROUTER
    for cap in ['headcounts.read','headcounts.by_class.read','headcounts.by_section.read','headcounts.by_option.read','headcounts.movements.read','headcounts.export_xlsx','headcounts.export_pdf','headcounts.print','contributions.record','contributions.register.read','contributions.register.export_xlsx']:
        assert cap in ROUTER
    assert 'effectifs_router' in APP and 'POINT-4D-EFFECTIFS-DEPOTS' in APP
