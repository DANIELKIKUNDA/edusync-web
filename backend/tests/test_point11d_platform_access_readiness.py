from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_point11d_backend_real_school_detail_and_readiness():
    s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text(encoding='utf-8')
    assert "/schools/{school_id}/detail" in s
    # schools module lot 2026-10: the sheet lives in schools_directory.py; tenant rows are read by platform_school_setup() (0078)
    d=(ROOT/'backend/src/edusync/modules/platform/application/schools_directory.py').read_text(encoding='utf-8')
    m=(ROOT/'backend/migrations/0078_schools_directory.sql').read_text(encoding='utf-8')
    for x in ["initial_admin","ready_count","platform_school_setup"]: assert x in d
    for x in ["academic_years","school_classes","fee_types"]: assert x in m

def test_point11d_access_governance_is_permissioned_audited_and_tenant_targeted():
    s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()
    assert "actor.require('platform.access.manage')" in s
    assert 'PLATFORM_MEMBERSHIP_DEACTIVATED' in s and 'PLATFORM_MEMBERSHIP_ACTIVATED' in s and 'PLATFORM_STANDARD_ROLE_ASSIGNED' in s
    assert "WHERE id=:id FOR UPDATE" in s
    m=(ROOT/'backend/migrations/0032_platform_access_governance.sql').read_text()
    assert 'platform.access.manage' in m and 'MANAGER_SYSTEME' in m and 'OWNER_APPROVED' in m

def test_point11d_frontend_has_real_school_governance_surface():
    # schools module lot 2026-10: the school sheet is platform/school_sheet.tsx. The platform governs only the school
    # administrator (no local business role from the platform), so the generic role picker is gone on purpose.
    s=(ROOT/'frontend/src/platform/school_sheet.tsx').read_text(encoding='utf-8')
    for x in ['SchoolSheetView','readiness','setMembershipActive','Désactiver','Réactiver','Réinitialiser']: assert x in s
    assert 'platformAssignRole' not in s
    api=(ROOT/'frontend/src/api.ts').read_text(encoding='utf-8')
    for x in ['platformSchoolDetail','platformRbacRoles','platformMembershipState','platformAssignRole']: assert x in api
