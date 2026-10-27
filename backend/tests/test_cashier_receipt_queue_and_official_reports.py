from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from uuid import UUID
import pytest
from fastapi import HTTPException
from edusync.modules.finance_checkout.api import router as checkout
from edusync.modules.finance_reports.api import router as reports
from edusync.shared.infrastructure.object_storage import ObjectStorageError
from edusync.shared.application.context import ActorContext
SID=UUID('00000000-0000-0000-0000-000000000001'); UID=UUID('00000000-0000-0000-0000-000000000002'); MID=UUID('00000000-0000-0000-0000-000000000003'); PID=UUID('00000000-0000-0000-0000-000000000004')
class Result:
 def __init__(self,row=None):self.row=row
 def mappings(self):return self
 def first(self):return self.row
class DB:
 def __init__(self,conn):self.conn=conn;self.committed=False;self.rolled_back=False
 @contextmanager
 def tenant_transaction(self,**_):
  try:yield self.conn;self.committed=True
  except Exception:self.rolled_back=True;raise
def actor():return ActorContext(school_id=SID,user_id=UID,membership_id=MID,permissions=frozenset(['finance.receipts.read','finance.receipts.print','finance.reports.periodic.generate']),capability_scopes=(('finance.reports.periodic.generate','SCHOOL',None),))

def test_pdf_request_does_not_claim_paper_was_printed(monkeypatch):
 class Repo:
  def __init__(self,conn):pass
  def receipt_facts(self,*_):return {'receipt_number':'REC-1','cashier':'Test','actor_user_id':UID}
  def receipt_copies(self,*_):return 0
  def print_settings(self,*_):return {'receipt_format':'80MM','receipt_copies':1}
  def record_receipt_print(self,*_):raise AssertionError('PDF request must not mark printed')
 monkeypatch.setattr(checkout,'PostgresFinanceCheckoutRepository',Repo)
 monkeypatch.setattr(checkout,'_school_for_receipt',lambda *_:{'name':'École'})
 monkeypatch.setattr(checkout,'receipt_pdf',lambda **_:b'%PDF-receipt')
 db=DB(object());response=checkout.print_receipt(PID,format=None,actor=actor(),services=SimpleNamespace(tenant_db=db))
 assert response.body==b'%PDF-receipt' and db.committed

def test_cashier_confirms_paper_separately(monkeypatch):
 events=[]
 class Conn:
  def execute(self,sql,params):
   if 'SELECT j.status,p.actor_user_id' in str(sql):return Result({'status':'PENDING','actor_user_id':UID})
   events.append(str(sql));return Result()
 class Repo:
  def __init__(self,conn):pass
  def receipt_copies(self,*_):return 0
  def record_receipt_print(self,*_):events.append('recorded');return 1
 monkeypatch.setattr(checkout,'PostgresFinanceCheckoutRepository',Repo)
 monkeypatch.setattr(checkout,'_audit_print',lambda *_:events.append('audited'))
 db=DB(Conn());result=checkout.receipt_queue_status(PID,checkout.ReceiptQueueStatusBody(status='PRINTED'),actor=actor(),services=SimpleNamespace(tenant_db=db))
 assert result['status']=='PRINTED' and db.committed and events[:2]==['recorded','audited']

def test_print_confirmation_is_idempotent(monkeypatch):
 class Conn:
  def execute(self,sql,params):
   if 'SELECT j.status,p.actor_user_id' in str(sql):
    return Result({'status':'PRINTED','actor_user_id':UID})
   raise AssertionError('A repeated confirmation must not write another copy or audit event')
 monkeypatch.setattr(checkout,'PostgresFinanceCheckoutRepository',lambda *_:(_ for _ in ()).throw(AssertionError('No extra copy')))
 db=DB(Conn())
 result=checkout.receipt_queue_status(PID,checkout.ReceiptQueueStatusBody(status='PRINTED'),actor=actor(),services=SimpleNamespace(tenant_db=db))
 assert result['status']=='PRINTED' and db.committed

def report_body():return reports.PeriodicPdfBody(profile_code='CONSOLIDE',period_type='JOURNALIER',start=date(2026,10,25),end=date(2026,10,25))
def test_official_archive_failure_rolls_back_number(monkeypatch):
 class Conn:
  def execute(self,sql,params):return Result(None)
 class Repo:
  def __init__(self,conn):pass
  def report_rows(self,*_,**__):return {'profile':{'title':'RAPPORT FINANCIER'},'totals':{},'partial_reporting_mode':'SEPARATE'}
  def register(self,*_,**__):return {'id':str(PID),'label':'RAP-001'}
 monkeypatch.setattr(reports,'PostgresPeriodicReportsRepository',Repo)
 monkeypatch.setattr(reports,'_school',lambda *_:{'name':'École'})
 monkeypatch.setattr(reports,'periodic_report_pdf',lambda **_:b'%PDF-report')
 monkeypatch.setattr(reports,'archive_official_pdf_strict',lambda *_a,**_k:(_ for _ in ()).throw(ObjectStorageError('unavailable')))
 db=DB(Conn())
 with pytest.raises(HTTPException) as exc:reports.periodic_pdf(report_body(),idempotency_key='report-2026-10-25-unique-001',actor=actor(),services=SimpleNamespace(tenant_db=db))
 assert exc.value.status_code==503 and db.rolled_back and not db.committed

def test_retry_returns_same_archived_bytes(monkeypatch):
 class Conn:
  def execute(self,sql,params):
   if 'FROM finance_generated_reports r LEFT JOIN generated_documents' in str(sql):return Result({'report_label':'RAP-001','profile_code':'CONSOLIDE','period_type':'JOURNALIER','start_date':date(2026,10,25),'end_date':date(2026,10,25),'generated_by':UID,'document_generation_id':PID,'object_key':f'schools/{SID}/documents/report.pdf'})
   return Result()
 monkeypatch.setattr(reports,'read_official_pdf',lambda *_:b'%PDF-original')
 monkeypatch.setattr(reports,'PostgresPeriodicReportsRepository',lambda *_:(_ for _ in ()).throw(AssertionError('must not register again')))
 db=DB(Conn());response=reports.periodic_pdf(report_body(),idempotency_key='report-2026-10-25-unique-001',actor=actor(),services=SimpleNamespace(tenant_db=db))
 assert response.body==b'%PDF-original' and response.headers['x-report-number']=='RAP-001' and response.headers['x-report-replayed']=='yes' and db.committed

def test_school_specific_profiles_are_not_global_defaults():
    result=reports.report_profiles(actor=actor())
    codes={p['code'] for p in result['profiles']}
    assert 'CONSOLIDE' in codes
    assert 'INSCRIPTION_JUIN' not in codes and 'JOURNAL_ECUSSON' not in codes
