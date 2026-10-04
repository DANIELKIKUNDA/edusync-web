from pathlib import Path
SQL=(Path(__file__).parents[1]/'migrations'/'0013_schooling_domain.sql').read_text(encoding='utf-8')

def test_terrain_first_enrollment_policy_defaults():
    assert "'required_student_fields',jsonb_build_array('last_name','middle_name','first_name','class_id')" in SQL
    assert "'guardian_required_at_enrollment',false" in SQL
    assert "'allow_profile_completion_later',true" in SQL

def test_birth_is_not_database_required():
    student_block=SQL.split('CREATE TABLE IF NOT EXISTS students',1)[1].split(');',1)[0]
    assert 'birth_date date,' in student_block
    assert 'birth_place varchar(160),' in student_block
    assert 'birth_date date NOT NULL' not in student_block
    assert 'birth_place varchar(160) NOT NULL' not in student_block

def test_guardian_is_distinct_from_family_and_many_to_many_link_exists():
    assert 'CREATE TABLE IF NOT EXISTS families' in SQL
    assert 'CREATE TABLE IF NOT EXISTS guardians' in SQL
    assert 'CREATE TABLE IF NOT EXISTS family_guardians' in SQL
    assert 'uq_family_one_primary_guardian' in SQL

def test_schooling_is_tenant_isolated_and_append_only_where_needed():
    assert 'FORCE ROW LEVEL SECURITY' in SQL
    assert 'validate_schooling_tenant_refs' in SQL
    assert 'forbid_schooling_delete' in SQL
    assert 'forbid_schooling_append_update' in SQL

def test_point4c_document_and_completion_capabilities_are_migrated():
    for code in ('students.directory.print_pdf','students.directory.export_xlsx','students.profile.print_pdf','families.directory.print_pdf','families.directory.export_xlsx','families.resolution.audit','students.profile.complete'):
        assert code in SQL
