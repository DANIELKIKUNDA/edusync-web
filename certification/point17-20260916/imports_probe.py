"""Official XLSX HTTP import workflow on isolated fixtures."""
import io,json,os
from pathlib import Path
from uuid import uuid4
import httpx
from openpyxl import load_workbook
root=Path(__file__).resolve().parents[2]
f=json.loads((root/'.local/http-fixtures.json').read_text(encoding='utf-8'))['A']
base=os.environ['EDUSYNC_API_BASE_URL'];assert base=='http://127.0.0.1:58000/api/v1'
results=[]
def req(c,method,path,expected=200,**kw):
 headers=kw.pop('headers',{})
 if method!='GET':headers.setdefault('Idempotency-Key',str(uuid4()))
 r=c.request(method,path,headers=headers,**kw);ok=r.status_code==expected
 results.append({'path':path,'status':r.status_code,'expected':expected,'pass':ok})
 print(('PASS ' if ok else 'FAIL ')+method+' '+path+': '+str(r.status_code),flush=True)
 if not ok:raise AssertionError(r.text[:180])
 return r
def filled(raw,values):
 wb=load_workbook(io.BytesIO(raw));ws=wb.worksheets[0]
 for j,v in enumerate(values,1):ws.cell(6,j,v)
 out=io.BytesIO();wb.save(out);return out.getvalue()
try:
 with httpx.Client(base_url=base+'/',timeout=90,headers={'Connection':'close'}) as c:
  r=req(c,'POST','auth/login',json={'scope':'SCHOOL','email':f['email'],'password':f['password'],'school_code':f['code']});c.headers['Authorization']='Bearer '+r.json()['access_token']
  contracts=req(c,'GET','import/contracts').json()
  assert len(contracts['contracts'])==3 and all(x['max_rows']==5000 for x in contracts['contracts'])
  for kind,path,values,params in [
   ('students','documents/student-import-template.xlsx',['IMPORT-'+uuid4().hex[:8],'Recette','Élève','F','CERT-1'],{'academic_year_id':f['year_id']}),
   ('staff','import/staff/template.xlsx',['CERT-'+uuid4().hex[:8],'Agent recette','Postnom','Prénom','F','ENSEIGNANT'],{}),
  ]:
   raw=req(c,'GET',path).content
   payload=filled(raw,values)
   preview=req(c,'POST',f'import/{kind}/analyze',params={'filename':'recette.xlsx',**params},content=payload).json()
   assert preview['total_rows']==1 and preview['error_rows']==0
   bid=preview['batch_id']
   req(c,'GET',f'import/batches/{kind}/{bid}/control-report.xlsx')
   if kind=='students':req(c,'POST',f'import/{kind}/batches/{bid}/execute',409,json={'accept_warnings':True})
   confirmation={'accept_warnings':True,'confirm_separate_households':True}
   first=req(c,'POST',f'import/{kind}/batches/{bid}/execute',json=confirmation).json()
   replay=req(c,'POST',f'import/{kind}/batches/{bid}/execute',json=confirmation).json()
   assert first['imported']==1 and replay['replayed'] is True
   wb=load_workbook(io.BytesIO(raw));wb.worksheets[0].cell(5,1,'COLONNE MODIFIÉE');out=io.BytesIO();wb.save(out)
   req(c,'POST',f'import/{kind}/analyze',400,params={'filename':'modifie.xlsx',**params},content=out.getvalue())
finally:
 (root/'certification/point17-20260916/imports-http.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
