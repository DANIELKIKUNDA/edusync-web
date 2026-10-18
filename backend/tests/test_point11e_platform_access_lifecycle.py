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
 # Schools module lot 2026-10: the platform governs only the school administrator. Its access is revoked from the
 # school sheet (membership deactivation, audited) and the generic local-role picker is gone on purpose.
 sheet=(ROOT/'frontend/src/platform/school_sheet.tsx').read_text(encoding='utf-8')
 assert 'setMembershipActive(' in sheet and 'Désactiver l’accès' in sheet and 'Retirer ce rôle' not in s
