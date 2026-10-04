"""HTTP BOLA checks with real, distinct school resources."""
import json,os
from pathlib import Path
from uuid import uuid4
import httpx
root=Path(__file__).resolve().parents[2];private=root/'.local/http-fixtures.json'
state=json.loads(private.read_text(encoding='utf-8'));results=[]
base=os.environ['EDUSYNC_API_BASE_URL'];assert base=='http://127.0.0.1:58000/api/v1'
def save():private.write_text(json.dumps(state,indent=2),encoding='utf-8')
def req(c,method,path,expected=200,**kw):
 headers=kw.pop('headers',{})
 if method!='GET':headers.setdefault('Idempotency-Key',str(uuid4()))
 r=c.request(method,path,headers=headers,**kw)
 ok=r.status_code in (expected if isinstance(expected,list) else [expected])
 results.append({'method':method,'path':path,'status':r.status_code,'expected':expected,'pass':ok})
 print(('PASS ' if ok else 'FAIL ')+method+' '+path+': '+str(r.status_code),flush=True)
 if not ok:raise AssertionError(r.text[:250])
 return r
def login(f):
 c=httpx.Client(base_url=base+'/',timeout=30,headers={'Connection':'close'})
 r=req(c,'POST','auth/login',json={'email':f['email'],'password':f['password'],'scope':'SCHOOL','school_code':f['code']})
 c.headers['Authorization']='Bearer '+r.json()['access_token'];return c
try:
 manager=httpx.Client(base_url=base+'/',timeout=30,headers={'Connection':'close'})
 token=req(manager,'POST','auth/login',json={'email':os.environ['EDUSYNC_PLATFORM_ADMIN_EMAIL'],'password':os.environ['EDUSYNC_PLATFORM_ADMIN_PASSWORD'],'scope':'PLATFORM'}).json()['access_token']
 manager.headers['Authorization']='Bearer '+token
 for name in ('A','B'):
  f=state[name]
  if not f.get('cashier_scope_verified'):
   req(manager,'POST',f"platform/memberships/{f['membership_id']}/roles",json={'role_code':'CAISSIER','reason':'Recette des inscriptions selon le catalogue métier existant'})
   f['cashier_role']=True;f['cashier_scope_verified']=True;save()
  c=login(f)
  if 'section_id' not in f:
   f['section_id']=req(c,'PUT','settings/sections/CERT',json={'code':'CERT','label':'Section recette','enabled':True}).json()['id'];save()
  if 'class_id' not in f:
   f['class_id']=req(c,'POST','settings/classes',201,json={'academic_year_id':f['year_id'],'section_id':f['section_id'],'code':'CERT-1','label':'Classe recette'}).json()['id'];save()
  years=req(c,'GET','settings/academic-years').json();year=next(y for y in years if y['id']==f['year_id'])
  if year['status']!='ACTIVE':req(c,'POST',f"settings/academic-years/{f['year_id']}/activate",headers={'If-Match':str(year['version'])})
  if 'family_id' not in f:
   data=req(c,'POST','schooling/enrollments/family',201,json={'primary_guardian':{'full_name':f'Tuteur recette {name}','is_primary':True},'children':[{'last_name':f'CERTIFICATION-{name}','middle_name':'Recette','first_name':'Élève test','gender':'F','class_id':f['class_id']}]}).json()
   f['family_id']=data['family_id'];save()
  family=req(c,'GET',f"schooling/families/{f['family_id']}").json()
  # Persist fixture resource ids only, never credentials in public artifacts.
  (root/f'.local/family-{name}.json').write_text(json.dumps(family,default=str),encoding='utf-8')
  f['student_id']=family['children'][0]['id'];f['guardian_id']=family['guardians'][0]['guardian_id'];save()
  c.close()
 for name in ('A','B'):
  f=state[name];other=state['B' if name=='A' else 'A'];c=login(f)
  req(c,'GET',f"schooling/students/{f['student_id']}")
  req(c,'GET',f"schooling/students/{other['student_id']}",404)
  req(c,'GET',f"schooling/families/{other['family_id']}",404)
  req(c,'PATCH',f"schooling/students/{other['student_id']}",404,json={'first_name':'Intrusion refusée'},headers={'If-Match':'1'})
  req(c,'DELETE',f"schooling/families/{other['family_id']}/guardians/{other['guardian_id']}",404)
  req(c,'GET',f"schooling/students/{other['student_id']}/profile.pdf",404)
  rows=req(c,'GET','schooling/students',params={'school_id':other['school_id'],'q':f'CERTIFICATION-{"B" if name=="A" else "A"}'}).json()
  assert other['student_id'] not in json.dumps(rows)
  c.close()
finally:
 (root/'certification/point17-20260916/schooling-http.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
