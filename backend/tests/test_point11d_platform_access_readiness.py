from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def test_point11d_backend_real_school_detail_and_readiness():
    s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()
    for x in ["/schools/{school_id}/detail","academic_years","school_classes","fee_types","initial_admin","ready_count"]: assert x in s

def test_point11d_access_governance_is_permissioned_audited_and_tenant_targeted():
    s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()
    assert "actor.require('platform.access.manage')" in s
    assert 'PLATFORM_MEMBERSHIP_DEACTIVATED' in s and 'PLATFORM_MEMBERSHIP_ACTIVATED' in s and 'PLATFORM_STANDARD_ROLE_ASSIGNED' in s
    assert "WHERE id=:id FOR UPDATE" in s
    m=(ROOT/'backend/migrations/0032_platform_access_governance.sql').read_text()
    assert 'platform.access.manage' in m and 'MANAGER_SYSTEME' in m and 'OWNER_APPROVED' in m

def test_point11d_frontend_has_real_school_governance_surface():
    s=(ROOT/'frontend/src/App.tsx').read_text()
    for x in ['PlatformSchoolDetailDialog','Fiche','readiness','platformMembershipState','platformAssignRole','Attribuer…','Désactiver','Réactiver']: assert x in s
    api=(ROOT/'frontend/src/api.ts').read_text()
    for x in ['platformSchoolDetail','platformRbacRoles','platformMembershipState','platformAssignRole']: assert x in api
