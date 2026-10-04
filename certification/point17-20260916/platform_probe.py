"""Read-only platform smoke probes; never logs credentials."""
import json
import os
from pathlib import Path
import httpx

root=Path(__file__).resolve().parents[2]
base=os.environ['EDUSYNC_API_BASE_URL']
assert base=='http://127.0.0.1:58000/api/v1'
fixtures=json.loads((root/'.local/http-fixtures.json').read_text(encoding='utf-8'))
results=[]
with httpx.Client(base_url=base+'/',timeout=30,headers={'Connection':'close'}) as c:
 r=c.post('auth/login',json={'email':os.environ['EDUSYNC_PLATFORM_ADMIN_EMAIL'],'password':os.environ['EDUSYNC_PLATFORM_ADMIN_PASSWORD'],'scope':'PLATFORM'})
 r.raise_for_status()
 c.headers['Authorization']='Bearer '+r.json()['access_token']
 for path in ['platform/dashboard','platform/schools-page','platform/access','platform/audit','platform/diagnostics','platform/system-notifications',f"platform/schools/{fixtures['A']['school_id']}/detail"]:
  r=c.get(path)
  result={'path':path,'status':r.status_code,'pass':r.status_code==200}
  if path=='platform/schools-page' and r.status_code==200:
   school=next(x for x in r.json()['items'] if x['id']==fixtures['A']['school_id'])
   result['expected_memberships']=1
   result['actual_memberships']=school['active_memberships']
   result['pass']=school['active_memberships']==1
  results.append(result)
  print(json.dumps(result),flush=True)
(root/'certification/point17-20260916/platform-http.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
assert all(x['pass'] for x in results)
