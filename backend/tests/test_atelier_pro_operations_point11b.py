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
    # Schools module lot 2026-10 (justified adaptation): the schools screen moved to platform/schools.tsx + school_sheet.tsx
    # and its SQL to application/schools_directory.py; same intent, new implementation.
    assert '<SchoolsModule ' in block and 'aria-modal="true"' in text('frontend/src/platform/account.tsx')   # shared Modal
    for rel in ('frontend/src/platform/schools.tsx','frontend/src/platform/school_sheet.tsx'):
        ui2=text(rel); assert 'window.confirm' not in ui2 and 'window.prompt' not in ui2 and 'window.alert' not in ui2
    assert 'function StatusDialog(' in text('frontend/src/platform/school_sheet.tsx')

def test_atelier_pro_directories_are_searchable_and_paginated():
    ui=text('frontend/src/App.tsx')
    # Schools module lot 2026-10 (justified adaptation): the schools screen moved to platform/schools.tsx + school_sheet.tsx
    # and its SQL to application/schools_directory.py; same intent, new implementation.
    schools=text('frontend/src/platform/schools.tsx')
    assert 'setQInput' in schools and 'next_cursor' in schools and 'Charger la suite' in schools
    # lot « Utilisateurs & accès » 2026-10: the accounts directory is platform/identities.tsx (instant search, keyset cursor)
    accounts=text('frontend/src/platform/identities.tsx')
    assert '<AccessDirectory ' in ui and 'setQInput' in accounts and 'next_cursor' in accounts and 'Charger la suite' in accounts
    # N1 certification 2026-10 (justified adaptation): the audit journal moved to platform/audit.tsx on the
    # filtered /platform/audit-log endpoint; it is still keyset-paginated by cursor (same intent).
    audit=text('frontend/src/platform/audit.tsx')
    assert 'setCursor(r.next_cursor)' in audit and 'auditLog(token, filters, more ? cursor : null)' in audit

def test_bootstrap_password_not_added_to_idempotency_payload():
    router=text('backend/src/edusync/modules/platform/api/router.py')
    section=router[router.index('def bootstrap_admin('):router.index('@router.get("/audit-count")')]
    assert '"password"' not in section.split('payload =',1)[1].split('try:',1)[0]
    # the server generates the temporary password; it lives only in this request and is never replayed
    assert 'new_temporary_password()' in section and 'issued.get("temporary_password")' in section
