"""Live session and delegated-platform checks, isolated fixtures only."""
import json,os,secrets
from pathlib import Path
from uuid import uuid4
import httpx

root=Path(__file__).resolve().parents[2]
private=root/'.local/http-fixtures.json'
fixtures=json.loads(private.read_text(encoding='utf-8'))
base=os.environ['EDUSYNC_API_BASE_URL'];assert base=='http://127.0.0.1:58000/api/v1'
results=[]
def req(c,method,path,expected=200,**kw):
 r=c.request(method,path,**kw)
 ok=r.status_code in (expected if isinstance(expected,list) else [expected])
 results.append({'method':method,'path':path,'status':r.status_code,'expected':expected,'pass':ok})
 print(('PASS' if ok else 'FAIL')+' '+method+' '+path+': '+str(r.status_code),flush=True)
 if not ok:raise AssertionError(path+': '+str(r.status_code))
 return r
def login(f,scope='SCHOOL'):
 c=httpx.Client(base_url=base+'/',timeout=30,headers={'Connection':'close'})
 data={'scope':scope,'email':f['email'],'password':f['password']}
 if scope=='SCHOOL':data['school_code']=f['code']
 r=req(c,'POST','auth/login',json=data)
 assert 'HttpOnly' in r.headers.get('set-cookie','')
 assert 'SameSite=lax' in r.headers.get('set-cookie','')
 c.headers['Authorization']='Bearer '+r.json()['access_token']
 return c

try:
 manager=login({'email':os.environ['EDUSYNC_PLATFORM_ADMIN_EMAIL'],'password':os.environ['EDUSYNC_PLATFORM_ADMIN_PASSWORD']},'PLATFORM')
 f=fixtures['B'];path=f"platform/collaborators/{f['user_id']}"
 req(manager,'POST',path+'/grant',json={'reason':'Recette locale des permissions déléguées'})
 try:
  collaborator=login(f,'PLATFORM')
  for p in ['platform/schools','platform/dashboard','platform/access','platform/audit','platform/diagnostics']:
   req(collaborator,'GET',p)
  req(collaborator,'GET','platform/system-notifications',403)
  for p,data in [(path+'/grant',{'reason':'Tentative auto-escalade de recette'}),(f"platform/schools/{f['school_id']}/suspend",{'reason':'Refus attendu en recette'}),(f"platform/schools/{f['school_id']}/bootstrap-admin",{'email':'denied@example.test','full_name':'Refus recette','password':secrets.token_urlsafe(24)})]:
   req(collaborator,'POST',p,403,json=data,headers={'Idempotency-Key':str(uuid4())})
 finally:
  req(manager,'POST',path+'/revoke',json={'reason':'Fin de recette des permissions déléguées'})
 req(collaborator,'POST','auth/refresh',401)
 req(collaborator,'GET','platform/schools',[401,403])
 audit=req(manager,'GET','platform/audit?limit=100').json()['items']
 assert {'PLATFORM_COLLABORATOR_GRANTED','PLATFORM_COLLABORATOR_REVOKED'} <= {a['action'] for a in audit if a['entity_id']==f['user_id']}
 collaborator.close();manager.close()
 a=login(fixtures['A'])
 req(a,'GET','auth/me',401,headers={'Authorization':'Bearer forged.invalid.token'})
 sessions=req(a,'GET','auth/sessions').json()['items']
 for s in sessions:
  if not s['revoked_at']:req(a,'POST',f"auth/sessions/{s['id']}/revoke",204)
 req(a,'POST','auth/refresh',401)
 a.close()
 a=login(fixtures['A']);new_password=secrets.token_urlsafe(24)
 req(a,'POST','auth/password',json={'current_password':fixtures['A']['password'],'new_password':new_password})
 fixtures['A']['password']=new_password;private.write_text(json.dumps(fixtures,indent=2),encoding='utf-8')
 req(a,'POST','auth/refresh',401)
 req(a,'GET','auth/me',401)
 a.close();login(fixtures['A']).close()
finally:
 (root/'certification/point17-20260916/sessions-platform-http.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
