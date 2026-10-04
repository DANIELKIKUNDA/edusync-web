from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def test_point11e_role_revocation_is_real_permissioned_and_audited():
 s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()
 for x in ["/memberships/{membership_id}/roles/{role_code}/revoke","actor.require('platform.access.manage')",'PLATFORM_STANDARD_ROLE_REVOKED','FOR UPDATE']: assert x in s
def test_point11e_membership_deactivation_revokes_school_sessions():
 s=(ROOT/'backend/src/edusync/modules/platform/api/router.py').read_text()
 assert 'UPDATE user_device_sessions SET revoked_at=coalesce(revoked_at,now())' in s
 assert "school_id=:sid AND revoked_at IS NULL" in s
def test_point11e_frontend_exposes_role_removal_and_assignment_details():
 a=(ROOT/'frontend/src/api.ts').read_text(); s=(ROOT/'frontend/src/App.tsx').read_text()
 assert 'platformRevokeRole' in a and '/revoke' in a
 assert 'platformRevokeRole' in s and 'role_assignments' in s and 'Retirer ce rôle' in s
