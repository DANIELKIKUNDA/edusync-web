from pathlib import Path
SQL=Path('migrations/0012_personnel_domain.sql').read_text(encoding='utf-8')

def test_personnel_tables_exist():
    for name in ['staff_members','staff_functions','staff_assignments','staff_status_history','staff_access_links','staff_student_links','staff_student_finance_preferences']:
        assert f'CREATE TABLE IF NOT EXISTS {name}' in SQL

def test_category_function_scope_and_titulariat_are_distinct_columns():
    for token in ['category varchar','function_id uuid','scope_type varchar','is_titular boolean','titular_class_id uuid']:
        assert token in SQL

def test_staff_identity_is_unique_per_school_not_global():
    assert 'UNIQUE(school_id, employee_no)' in SQL

def test_no_physical_delete_for_personnel_history():
    assert 'REVOKE DELETE ON staff_members' in SQL
    assert 'forbid_personnel_delete' in SQL
    assert 'staff_status_history is append-only' in SQL

def test_exit_account_model_links_membership_not_global_user():
    assert 'staff_access_links' in SQL and 'membership_id uuid NOT NULL REFERENCES school_memberships' in SQL

def test_child_link_is_explicit_and_student_fk_is_deferred():
    assert 'staff_student_links' in SQL
    assert 'student_id uuid NOT NULL' in SQL
    assert 'never inferred from guardian name/phone' in SQL

def test_personnel_is_force_rls_tenant_scoped():
    assert "ALTER TABLE %I FORCE ROW LEVEL SECURITY" in SQL
    assert "app.current_school_id" in SQL

def test_exact_open_assignment_and_primary_guards():
    assert 'uq_staff_assignment_open_exact' in SQL
    assert 'uq_staff_one_primary_open' in SQL

def test_cross_school_reference_guard_exists():
    assert 'validate_personnel_tenant_refs' in SQL
    for msg in ['Agent hors école','Fonction hors école','Section hors école','Classe hors école']:
        assert msg in SQL

def test_new_output_and_lifecycle_capabilities_are_registered():
    for cap in ['personnel.directory.print_pdf','personnel.directory.export_xlsx','personnel.profile.print_pdf','personnel.history.read','personnel.exit','personnel.reactivate','personnel.access_link.manage']:
        assert cap in SQL

def test_consultation_roles_receive_exports_but_not_mutations():
    assert "('PROMOTEUR','personnel.directory.print_pdf')" in SQL
    assert "('PREFET_ETUDES','personnel.directory.export_xlsx')" in SQL
    # No baseline assignment gives mutation to Promoteur.
    assert "('PROMOTEUR','personnel.exit')" not in SQL
    assert "('GESTIONNAIRE','personnel.create')" not in SQL
