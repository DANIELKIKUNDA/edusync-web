from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def read(p): return (ROOT/p).read_text(encoding='utf-8')

def test_platform_collaborator_is_least_privilege():
    sql=read('backend/migrations/0036_platform_collaborator_role.sql')
    assert 'COLLABORATEUR_PLATEFORME' in sql
    for cap in ('platform.schools.read','platform.audit.read','platform.health.read'):
        assert cap in sql
    for forbidden in ('platform.schools.suspend','platform.schools.create','platform.school_admin.bootstrap'):
        assert forbidden not in sql
    assert 'platform.collaborators.manage' in sql and "r.code='MANAGER_SYSTEME'" in sql

def test_platform_collaboration_is_audited_and_revokes_sessions():
    api=read('backend/src/edusync/modules/platform/api/router.py')
    assert "actor.require('platform.collaborators.manage')" in api
    assert 'PLATFORM_COLLABORATOR_GRANTED' in api
    assert 'PLATFORM_COLLABORATOR_REVOKED' in api
    assert 'PLATFORM_ROLE_REVOKED' in api
    assert 'FOR UPDATE' in api

def test_platform_login_uses_active_rbac_role_and_refresh_uses_canonical_membership_table():
    iam=read('backend/src/edusync/modules/iam/api/router.py')
    assert "effective_role_assignments(user.id, None)" in iam
    assert 'FROM school_memberships WHERE id=:id' in iam
    assert 'FROM memberships WHERE id=:id' not in iam

def test_mobile_metrics_are_compact_two_by_two():
    css=read('frontend/src/styles.css')
    rule='.kpis,.schoolingKpis,.personMetrics,.effectifsKpis,.homeKpis{display:grid!important;grid-template-columns:repeat(2,minmax(0,1fr))!important'
    assert rule in css
    assert '@media(max-width:360px)' in css

def test_platform_access_ui_exposes_manager_controlled_collaboration():
    app=read('frontend/src/App.tsx')
    assert 'Collaborateur plateforme' in app
    assert 'Donner accès plateforme' in app
    assert 'platformGrantCollaborator' in app and 'platformRevokeCollaborator' in app
