from edusync.adapters.structure_scope import scoped_structure

SECTIONS=[{'id':'s','code':'SECONDAIRE'},{'id':'p','code':'PRIMAIRE'},{'id':'m','code':'MATERNELLE'}]
CLASSES=[{'id':'a','code':'7A','section_id':'s','section_code':'SECONDAIRE','option_id':'o'}, {'id':'b','code':'1P','section_id':'p','section_code':'PRIMAIRE','option_id':None}]
OPTIONS=[{'id':'o','section_id':'s'},{'id':'x','section_id':'p'}]

def test_section_picker_contains_only_its_sections_classes_and_options():
    r=scoped_structure(SECTIONS,CLASSES,OPTIONS,[('SECTION','secondaire')])
    assert not r['school_wide']
    assert [s['code'] for s in r['sections']]==['SECONDAIRE']
    assert [c['code'] for c in r['classes']]==['7A']
    assert [o['id'] for o in r['options']]==['o']

def test_explicit_school_grant_and_fused_sections():
    assert scoped_structure(SECTIONS,CLASSES,OPTIONS,[('SCHOOL',None)])['sections']==SECTIONS
    r=scoped_structure(SECTIONS,CLASSES,OPTIONS,[('SECTION','MATERNELLE'),('CYCLE','PRIMAIRE')])
    assert [s['code'] for s in r['sections']]==['PRIMAIRE','MATERNELLE']
    assert not r['school_wide']

def test_class_scope_and_no_scope_never_widen():
    r=scoped_structure(SECTIONS,CLASSES,OPTIONS,[('CLASS','7a')])
    assert [s['code'] for s in r['sections']]==['SECONDAIRE']
    assert [c['code'] for c in r['classes']]==['7A']
    for scopes in [[],[('UNKNOWN','SECONDAIRE')]]:
        r=scoped_structure(SECTIONS,CLASSES,OPTIONS,scopes)
        assert not any(r[k] for k in ('sections','classes','options','school_wide'))

def test_staff_visibility_executes_current_assignment_dates_and_section_isolation():
    from datetime import date,timedelta
    from sqlalchemy import create_engine,text
    from edusync.adapters.postgres_personnel import _scope_where,_bind_scope
    engine=create_engine('sqlite://')
    today=date.today()
    with engine.begin() as c:
        c.execute(text('CREATE TABLE staff_members(id TEXT,school_id TEXT)'))
        c.execute(text('CREATE TABLE staff_assignments(staff_id TEXT,school_id TEXT,scope_type TEXT,scope_value TEXT,class_id TEXT,start_date DATE,end_date DATE)'))
        c.execute(text('CREATE TABLE school_classes(id TEXT,school_id TEXT,section_id TEXT)'))
        c.execute(text('CREATE TABLE school_sections(id TEXT,school_id TEXT,code TEXT)'))
        for sid,section,start,end in [('active','SECONDAIRE',-1,None),('planned_end','SECONDAIRE',-1,1),('ended','SECONDAIRE',-2,0),('future','SECONDAIRE',1,None),('primary','PRIMAIRE',-1,None)]:
            c.execute(text('INSERT INTO staff_members VALUES(:id,\'school\')'),{'id':sid})
            c.execute(text("INSERT INTO staff_assignments VALUES(:id,'school','SECTION',:section,NULL,:start,:end)"),{'id':sid,'section':section,'start':str(today+timedelta(days=start)),'end':None if end is None else str(today+timedelta(days=end))})
        where,args=_scope_where((('SECTION','SECONDAIRE'),))
        found=c.execute(_bind_scope(text(f'SELECT sm.id FROM staff_members sm WHERE {where}'),args),args).scalars().all()
        assert set(found)=={'active','planned_end'}

def test_selector_uses_only_the_requested_capability(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace
    from edusync.modules.settings.api import router as R
    class Repo:
        def __init__(self,conn):pass
        def list_sections(self,*a):return SECTIONS
        def list_classes(self,*a):return CLASSES
        def list_options(self,*a):return OPTIONS
    @contextmanager
    def transaction(**kw):yield object()
    monkeypatch.setattr(R,'PostgresSettingsRepository',Repo)
    actor=SimpleNamespace(school_id='school',user_id='user',require=lambda cap:None,scopes_for=lambda cap:[('SCHOOL',None)] if cap=='settings.structure.read' else [('SECTION','SECONDAIRE')])
    result=R.structure_selector(capability='headcounts.by_class.read',year_id=None,actor=actor,services=SimpleNamespace(tenant_db=SimpleNamespace(tenant_transaction=transaction)))
    assert not result['school_wide'] and [s['code'] for s in result['sections']]==['SECONDAIRE']
