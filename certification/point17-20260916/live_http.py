"""HTTP certification fixtures and probes against the isolated local instance."""
from pathlib import Path
import json
import os
import secrets
from uuid import uuid4
import httpx

ROOT=Path(__file__).resolve().parents[2]
BASE=os.environ['EDUSYNC_API_BASE_URL']
assert BASE=='http://127.0.0.1:58000/api/v1', 'Local certification API required'
PRIVATE=ROOT/'.local/http-fixtures.json'
state=json.loads(PRIVATE.read_text(encoding='utf-8')) if PRIVATE.exists() else {}
results=[]
def save(): PRIVATE.write_text(json.dumps(state,indent=2),encoding='utf-8')
def request(client,method,path,expected=200,**kwargs):
    headers=kwargs.pop('headers',{})
    if method not in ('GET','HEAD'): headers.setdefault('Idempotency-Key',str(uuid4()))
    r=client.request(method,path,headers=headers,**kwargs)
    ok=r.status_code in ([expected] if isinstance(expected,int) else expected)
    results.append({'method':method,'path':path,'status':r.status_code,'expected':expected,'pass':ok})
    print(f'{"PASS" if ok else "FAIL"} {method} {path}: {r.status_code}',flush=True)
    if not ok: raise RuntimeError(f'{method} {path}: HTTP {r.status_code}; {r.text[:200]}')
    return r
def login(data,scope='SCHOOL'):
    c=httpx.Client(base_url=BASE+'/',timeout=30)
    body={'email':data['email'],'password':data['password'],'scope':scope}
    if scope=='SCHOOL':body['school_code']=data['code']
    r=request(c,'POST','auth/login',json=body)
    c.headers['Authorization']='Bearer '+r.json()['access_token']
    return c

try:
    manager=login({'email':os.environ['EDUSYNC_PLATFORM_ADMIN_EMAIL'],'password':os.environ['EDUSYNC_PLATFORM_ADMIN_PASSWORD']},'PLATFORM')
    for name in ('A','B'):
        if name not in state:
            suffix=uuid4().hex[:8]
            state[name]={'code':f'CERT-{name}-{suffix}','email':f'cert-{name}-{suffix}@example.test','password':secrets.token_urlsafe(24)};save()
        fixture=state[name]
        if 'school_id' not in fixture:
            r=request(manager,'POST','platform/schools',201,json={'code':fixture['code'],'name':f'École {name} — recette locale'},headers={'Idempotency-Key':'cert-school-'+fixture['code']})
            fixture['school_id']=r.json()['id'];save()
        if 'membership_id' not in fixture:
            r=request(manager,'POST',f"platform/schools/{fixture['school_id']}/bootstrap-admin",201,json={'email':fixture['email'],'full_name':f'Agent recette {name}','password':fixture['password']},headers={'Idempotency-Key':'cert-admin-'+fixture['code']})
            fixture.update(r.json());save()
        if not fixture.get('roles'):
            for role in ('SECRETARIAT','RESPONSABLE_FINANCE','INTENDANT'):
                request(manager,'POST',f"platform/memberships/{fixture['membership_id']}/roles",json={'role_code':role,'reason':'Certification locale isolée des modules et accès inter-écoles'})
            fixture['roles']=True;save()
        if not fixture.get('manager_role'):
            request(manager,'POST',f"platform/memberships/{fixture['membership_id']}/roles",json={'role_code':'GESTIONNAIRE','reason':'Profil de recette des consultations transversales'})
            fixture['manager_role']=True;save()
        c=login(fixture)
        request(c,'GET','auth/me')
        if 'year_id' not in fixture:
            r=request(c,'POST','settings/academic-years',201,json={'code':'2026-2027','label':'Année 2026-2027','start_date':'2026-09-01','end_date':'2027-07-31'},headers={'Idempotency-Key':'cert-year-'+fixture['code']})
            fixture['year_id']=r.json()['id'];save()
        c.close()
    for name in ('A','B'):
        c=login(state[name])
        for path in ['settings/overview','settings/academic-years','settings/sections','settings/classes','settings/fee-types','schooling/summary','schooling/students','schooling/families','personnel/summary','personnel','auth/sessions','import/batches/students','import/batches/finance-history']:
            request(c,'GET',path)
        other=state['B' if name=='A' else 'A']
        years=request(c,'GET','settings/academic-years',params={'school_id':other['school_id']}).json()
        assert all(y['id']!=other['year_id'] for y in years)
        request(c,'PUT',f"settings/academic-years/{other['year_id']}",404,json={'code':'2026-2027','label':'Tentative inter-écoles','start_date':'2026-09-01','end_date':'2027-07-31'},headers={'If-Match':'1'})
        request(c,'POST','auth/refresh')
        request(c,'POST','auth/logout',204)
        request(c,'POST','auth/refresh',401)
        c.close()
finally:
    (ROOT/'certification/point17-20260916/live-http.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
