"""Historical import must never create cash payments or receipts."""
import io,json,os
from pathlib import Path
from uuid import uuid4
import httpx
from openpyxl import load_workbook
from sqlalchemy import create_engine,text
from edusync.bootstrap.settings import Settings
root=Path(__file__).resolve().parents[2];cfg=Settings();assert ':55432/edusync_certification' in cfg.owner_database_url
f=json.loads((root/'.local/http-fixtures.json').read_text(encoding='utf-8'))['A']
family=json.loads((root/'.local/family-A.json').read_text(encoding='utf-8'));child=family['children'][0]
engine=create_engine(cfg.owner_database_url);charge=uuid4();label='HIST-'+uuid4().hex[:8];results=[]
base=os.environ['EDUSYNC_API_BASE_URL'];assert base=='http://127.0.0.1:58000/api/v1'
def req(c,method,path,expected=200,**kw):
 headers=kw.pop('headers',{});headers.setdefault('Idempotency-Key',str(uuid4()))
 r=c.request(method,path,headers=headers,**kw);ok=r.status_code==expected
 results.append({'path':path,'status':r.status_code,'expected':expected,'pass':ok});print(('PASS ' if ok else 'FAIL ')+path+': '+str(r.status_code),flush=True)
 if not ok:raise AssertionError(r.text[:180])
 return r
def cash_counts():
 with engine.connect() as c:return tuple(c.execute(text('SELECT (SELECT count(*) FROM finance_payments WHERE school_id=:s),(SELECT count(*) FROM finance_cash_sessions WHERE school_id=:s),(SELECT count(*) FROM finance_cash_events WHERE school_id=:s)'),{'s':f['school_id']}).one())
before=cash_counts()
with engine.begin() as c:c.execute(text("INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount) VALUES(:id,:s,:e,:l,'CDF',1000)"),{'id':charge,'s':f['school_id'],'e':child['enrollment_id'],'l':label})
try:
 with httpx.Client(base_url=base+'/',timeout=90,headers={'Connection':'close'}) as c:
  r=req(c,'POST','auth/login',json={'scope':'SCHOOL','email':f['email'],'password':f['password'],'school_code':f['code']});c.headers['Authorization']='Bearer '+r.json()['access_token']
  raw=req(c,'GET','import/finance-history/template.xlsx').content
  wb=load_workbook(io.BytesIO(raw));ws=wb.worksheets[0]
  for j,v in enumerate(['2026-2027',child['matricule'],label,None,100,'CDF','2026-09-01','CERT-'+str(charge),'Recette historique isolée'],1):ws.cell(6,j,v)
  out=io.BytesIO();wb.save(out);payload=out.getvalue()
  preview=req(c,'POST','import/finance-history/analyze',params={'filename':'historique.xlsx'},content=payload).json()
  assert preview['error_rows']==0,preview.get('preview')
  bid=preview['batch_id'];path=f'import/finance-history/batches/{bid}/execute'
  req(c,'POST',path,409,json={'accept_warnings':True})
  result=req(c,'POST',path,json={'accept_warnings':True,'confirm_outside_cash':True}).json()
  replay=req(c,'POST',path,json={'accept_warnings':True,'confirm_outside_cash':True}).json()
  assert result['cash_created'] is False and result['receipt_created'] is False and replay['replayed'] is True
  assert cash_counts()==before
  with engine.connect() as db:
   assert db.execute(text('SELECT count(*) FROM financial_history_import_ledger WHERE charge_id=:id'),{'id':charge}).scalar_one()==1
   assert db.execute(text('SELECT paid_amount FROM finance_charges WHERE id=:id'),{'id':charge}).scalar_one()==0
  again=req(c,'POST','import/finance-history/analyze',params={'filename':'historique.xlsx'},content=payload).json()
  assert again['error_rows']==1
  results.append({'check':'No cash/session/receipt created; one regularization only; historical duplicate rejected','pass':True})
finally:
 (root/'certification/point17-20260916/finance-history-http.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
