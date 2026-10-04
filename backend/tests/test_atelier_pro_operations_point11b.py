from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def text(rel): return (ROOT/rel).read_text(encoding='utf-8')

def test_atelier_pro_sensitive_school_operations_are_wired():
    api=text('frontend/src/api.ts'); ui=text('frontend/src/App.tsx'); router=text('backend/src/edusync/modules/platform/api/router.py')
    for name in ('platformSuspendSchool','platformReactivateSchool','platformBootstrapAdmin'):
        assert name in api and name in ui
    for route in ('/schools/{school_id}/suspend','/schools/{school_id}/reactivate','/schools/{school_id}/bootstrap-admin'):
        assert route in router
    for cap in ('platform.schools.suspend','platform.schools.activate','platform.school_admin.bootstrap'):
        assert cap in text('backend/src/edusync/modules/platform/application/use_cases.py')

def test_atelier_pro_does_not_use_native_confirmation_prompts():
    ui=text('frontend/src/App.tsx')
    block=ui[ui.index('function AtelierPro'):ui.index('const parameterTabs=')]
    assert 'window.confirm' not in block and 'window.prompt' not in block and 'window.alert' not in block
    assert 'PlatformSchoolActionDialog' in block and 'aria-modal="true"' in block

def test_atelier_pro_directories_are_searchable_and_paginated():
    ui=text('frontend/src/App.tsx')
    assert 'searchSchools' in ui and 'searchAccess' in ui
    assert "schools.offset+schools.limit" in ui
    assert "access.offset+access.limit" in ui
    assert "audit.next_cursor" in ui

def test_bootstrap_password_not_added_to_idempotency_payload():
    router=text('backend/src/edusync/modules/platform/api/router.py')
    section=router[router.index('def bootstrap_admin('):router.index('@router.get("/audit-count")')]
    assert '"password"' not in section.split('payload =',1)[1].split('try:',1)[0]
    assert 'password is consumed only' in section
