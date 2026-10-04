import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
CONTRACT=ROOT/'contracts'/'POINT3B_ROLE_DECISIONS_FINAL.json'
MIGRATION=ROOT/'backend'/'migrations'/'0009_secondary_leadership_roles.sql'

def role(code):
    data=json.loads(CONTRACT.read_text(encoding='utf-8'))
    return next(r for r in data['roles'] if r['code']==code)

def test_secondary_leadership_roles_exist_and_are_locked():
    for code in ('DIRECTEUR_ETUDES','DIRECTEUR_DISCIPLINE'):
        r=role(code)
        assert r['owner_decision']=='APPROVED'
        assert r['status']=='LOCKED_OWNER_APPROVED'
        assert r['scope_policy']['required_scope_type']=='SECTION'
        assert r['scope_policy']['allowed_scope_values']==['SECONDAIRE']

def test_directeur_etudes_finance_is_optional_not_default():
    caps=set(role('DIRECTEUR_ETUDES')['final_capabilities'])
    assert not any(c.startswith('finance.') for c in caps)
    assert 'students.read' in caps
    assert 'personnel.read' in caps
    assert 'headcounts.read' in caps

def test_directeur_discipline_has_parent_communications_but_no_finance_default():
    caps=set(role('DIRECTEUR_DISCIPLINE')['final_capabilities'])
    assert {'communications.send.individual','communications.send.class','communications.send.section','communications.sms.send'} <= caps
    assert not any(c.startswith('finance.') for c in caps)

def test_database_scope_guard_is_secondary_only():
    sql=MIGRATION.read_text(encoding='utf-8')
    assert "'DIRECTEUR_ETUDES'" in sql and "'DIRECTEUR_DISCIPLINE'" in sql
    assert "NEW.scope_type <> 'SECTION'" in sql
    assert "SECONDAIRE" in sql
