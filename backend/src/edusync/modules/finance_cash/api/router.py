from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text
from edusync.adapters.postgres_cash_integrity import PostgresCashIntegrityRepository,SupervisorRequired
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from fastapi import Header as _HeaderE
from edusync.adapters.postgres_idempotency import PostgresIdempotencyRepository
from edusync.shared.application.idempotency import IdempotencyConflict,IdempotencyInProgress,IdempotentExecutor
router=APIRouter(tags=['Centre financier · Caisse'])
def need(a,c):
 try:a.require(c)
 except PermissionError as e:raise HTTPException(403,str(e))
def one(conn,q,p):
 r=conn.execute(text(q),p).mappings().first();return dict(r) if r else None
def totals(conn,sid):
 rows=conn.execute(text("""SELECT currency,COALESCE(sum(amount),0) amount FROM finance_payments WHERE cash_session_id=:s GROUP BY currency"""),{'s':str(sid)}).mappings().all()
 exp=conn.execute(text("""SELECT currency,COALESCE(sum(amount),0) amount FROM finance_cash_expenses WHERE cash_session_id=:s GROUP BY currency"""),{'s':str(sid)}).mappings().all()
 return {str(x['currency']):str(x['amount']) for x in rows},{str(x['currency']):str(x['amount']) for x in exp}
def projection(conn,row):
 receipts,expenses=totals(conn,row['id']); out=dict(row); ci=PostgresCashIntegrityRepository(conn); rev=ci.session_reversals(row['id']); adv=ci.session_advance_funds(row['id'])
 for cur in ('CDF','USD'):
  opening=Decimal(str(row.get('opening_'+cur.lower()) or 0)); inc=Decimal(receipts.get(cur,'0'))+Decimal(adv.get(cur,'0')); ex=Decimal(expenses.get(cur,'0')); rv=Decimal(rev.get(cur,'0')); expected=opening+inc-ex-rv
  out[cur.lower()]={'opening':str(opening),'receipts':str(inc),'expenses':str(ex),'reversals':str(rv),'expected_cash':str(expected),'counted':str(row.get('counted_'+cur.lower())) if row.get('counted_'+cur.lower()) is not None else None,'variance':str(Decimal(str(row.get('counted_'+cur.lower())))-expected) if row.get('counted_'+cur.lower()) is not None else None}
 return out
@router.get('/current')
def current(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.cash.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=one(c,"SELECT * FROM finance_cash_sessions WHERE school_id=:sid AND membership_id=:mid AND status='OPEN' ORDER BY opened_at DESC LIMIT 1",{'sid':str(actor.school_id),'mid':str(actor.membership_id)})
  return {'session':projection(c,r) if r else None}
class OpenBody(BaseModel): opening_cdf:Decimal=Field(default=0,ge=0);opening_usd:Decimal=Field(default=0,ge=0)
@router.post('/open')
def open_cash(b:OpenBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.cash.open')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  if one(c,"SELECT id FROM finance_cash_sessions WHERE school_id=:sid AND membership_id=:mid AND status='OPEN' FOR UPDATE",{'sid':str(actor.school_id),'mid':str(actor.membership_id)}):raise HTTPException(409,'Votre caisse est déjà ouverte')
  try:ci=PostgresCashIntegrityRepository(c);ci.require_day_open(actor.school_id,ci.today())
  except ValueError as e:raise HTTPException(409,str(e)) from e
  r=one(c,"""INSERT INTO finance_cash_sessions(school_id,membership_id,business_date,opening_cdf,opening_usd) VALUES(:sid,:mid,CURRENT_DATE,:cdf,:usd) RETURNING *""",{'sid':str(actor.school_id),'mid':str(actor.membership_id),'cdf':b.opening_cdf,'usd':b.opening_usd})
  c.execute(text("INSERT INTO finance_cash_events(school_id,cash_session_id,actor_user_id,event_type,payload) VALUES(:sid,:cs,:u,'OPEN',jsonb_build_object('opening_cdf',:cdf,'opening_usd',:usd))"),{'sid':str(actor.school_id),'cs':str(r['id']),'u':str(actor.user_id),'cdf':b.opening_cdf,'usd':b.opening_usd})
  return projection(c,r)
class CloseBody(BaseModel): counted_cdf:Decimal=Field(ge=0);counted_usd:Decimal=Field(ge=0);note:str|None=Field(default=None,max_length=500)
@router.post('/close')
def close_cash(b:CloseBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.cash.close')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=one(c,"SELECT * FROM finance_cash_sessions WHERE school_id=:sid AND membership_id=:mid AND status='OPEN' FOR UPDATE",{'sid':str(actor.school_id),'mid':str(actor.membership_id)})
  if not r:raise HTTPException(409,'Aucune caisse ouverte à clôturer')
  c.execute(text("UPDATE finance_cash_sessions SET status='CLOSED',closed_at=now(),counted_cdf=:cdf,counted_usd=:usd,close_note=:n WHERE id=:id"),{'cdf':b.counted_cdf,'usd':b.counted_usd,'n':b.note,'id':str(r['id'])})
  c.execute(text("INSERT INTO finance_cash_events(school_id,cash_session_id,actor_user_id,event_type,payload) VALUES(:sid,:cs,:u,'CLOSE',jsonb_build_object('counted_cdf',:cdf,'counted_usd',:usd))"),{'sid':str(actor.school_id),'cs':str(r['id']),'u':str(actor.user_id),'cdf':b.counted_cdf,'usd':b.counted_usd})
  r=one(c,'SELECT * FROM finance_cash_sessions WHERE id=:id',{'id':str(r['id'])});return projection(c,r)
@router.get('/history')
def history(day:str|None=Query(None),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.cash.read');other='finance.cash.other.read' in actor.permissions
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  q="SELECT * FROM finance_cash_sessions WHERE school_id=:sid AND business_date=COALESCE(CAST(:day AS date),CURRENT_DATE)"+('' if other else ' AND membership_id=:mid')+' ORDER BY opened_at DESC'
  rows=c.execute(text(q),{'sid':str(actor.school_id),'day':day,'mid':str(actor.membership_id)}).mappings().all();return {'items':[projection(c,dict(r)) for r in rows]}

@router.get('/day-summary')
def day_summary(day:str|None=Query(None),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.cash.other.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  rows=c.execute(text("SELECT * FROM finance_cash_sessions WHERE school_id=:sid AND business_date=COALESCE(CAST(:day AS date),CURRENT_DATE) ORDER BY opened_at"),{'sid':str(actor.school_id),'day':day}).mappings().all()
  totals={cur:{'opening':Decimal('0'),'receipts':Decimal('0'),'expenses':Decimal('0'),'expected_cash':Decimal('0')} for cur in ('CDF','USD')}
  projected=[]
  for raw in rows:
   item=projection(c,dict(raw));projected.append(item)
   for cur,key in (('CDF','cdf'),('USD','usd')):
    for field in ('opening','receipts','expenses','reversals','expected_cash'):totals[cur][field]=totals[cur].get(field,Decimal('0'))+Decimal(item[key][field])
  sup=PostgresCashIntegrityRepository(c).supervisor_reversals(actor.school_id,day)
  for cur in ('CDF','USD'):totals[cur]['supervisor_reversals']=Decimal(sup.get(cur,'0'));totals[cur]['expected_cash']-=totals[cur]['supervisor_reversals']
  return {'business_date':day,'open_count':sum(1 for x in projected if x['status']=='OPEN'),'closed_count':sum(1 for x in projected if x['status']=='CLOSED'),'currencies':{cur:{k:str(v) for k,v in vals.items()} for cur,vals in totals.items()},'sessions':projected}

@router.get('/{session_id}/journal')
def journal(session_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.cash.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=one(c,'SELECT * FROM finance_cash_sessions WHERE id=:id AND school_id=:sid',{'id':str(session_id),'sid':str(actor.school_id)})
  if not r:raise HTTPException(404,'Caisse introuvable')
  if str(r['membership_id'])!=str(actor.membership_id) and 'finance.cash.other.read' not in actor.permissions:raise HTTPException(403,'Cette caisse appartient à un autre caissier')
  items=c.execute(text("""SELECT p.created_at,'RECEIPT' kind,p.receipt_number reference,p.amount,p.currency,CAST(p.id AS text) payment_id,EXISTS(SELECT 1 FROM finance_payment_reversals x WHERE x.payment_id=p.id) reversed FROM finance_payments p WHERE p.cash_session_id=:id UNION ALL SELECT e.created_at,'EXPENSE',e.label,e.amount,e.currency,NULL,false FROM finance_cash_expenses e WHERE e.cash_session_id=:id UNION ALL SELECT r.performed_at,r.reversal_type,p.receipt_number,r.amount,r.currency,NULL,false FROM finance_payment_reversals r JOIN finance_payments p ON p.id=r.payment_id WHERE r.cash_session_id=:id UNION ALL SELECT f.received_at,'ADVANCE_FUND',f.receipt_number,f.amount,f.currency,NULL,false FROM finance_advance_funds f WHERE f.cash_session_id=:id ORDER BY created_at"""),{'id':str(session_id)}).mappings().all()
  return {'session':projection(c,r),'items':[dict(x) for x in items]}


# ---------------------------------------------------------------- N3-B (Desktop parity, owner decision 2026-10-15)
import json as _json
from datetime import date as _date
from io import BytesIO as _BytesIO
from fastapi import Header as _Header
from fastapi.responses import StreamingResponse as _Stream
from edusync.modules.finance_cash.application.documents import cash_journal_pdf,daily_report_pdf
from edusync.modules.documents.application.object_store import archive_generated_tx
def _audit(c,actor,action,entity_type,entity_id,old,new,reason=None):
 c.execute(text("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,old_json,new_json)
  VALUES(:sid,:uid,:mid,:a,:et,:eid,'WEB',CAST(:o AS jsonb),CAST(:n AS jsonb))"""),{'sid':str(actor.school_id),'uid':str(actor.user_id),'mid':str(actor.membership_id),
  'a':action,'et':entity_type,'eid':str(entity_id),'o':_json.dumps(old,default=str) if old is not None else None,'n':_json.dumps({**(new or {}),**({'reason':reason} if reason else {})},default=str)})
def _names(services,ops):
 # users is readable by the tenant role only for the caller's own row: other names are resolved by the platform role.
 missing={str(o['user_id']) for o in ops if not o.get('user_name') and o.get('user_id')}
 if missing:
  with services.platform_db.platform_transaction() as pc:
   names={str(r[0]):r[1] for r in pc.execute(text("SELECT id,full_name FROM users WHERE id=ANY(CAST(:ids AS uuid[]))"),{'ids':list(missing)}).all()}
  for o in ops:
   if not o.get('user_name') and o.get('user_id'):o['user_name']=names.get(str(o['user_id']))
 return ops
def _day(v):
 try:return _date.fromisoformat(v) if v else None
 except ValueError as e:raise HTTPException(422,'Date invalide') from e
def _report(c,actor,day):
 ci=PostgresCashIntegrityRepository(c);return ci.day_report(actor.school_id,_day(day) or ci.today())
def _school_name(c,sid):return c.execute(text("SELECT name FROM schools WHERE id=:s"),{'s':str(sid)}).scalar_one_or_none() or 'École'

class ExpenseBody(BaseModel):
 category:str=Field(min_length=1,max_length=80);amount:Decimal=Field(gt=0,max_digits=18,decimal_places=2);currency:str=Field(pattern='^(CDF|USD)$')
 reason:str=Field(min_length=3,max_length=500);reference:str|None=Field(default=None,max_length=80)
@router.post('/expenses',status_code=201)
def record_expense(b:ExpenseBody,idempotency_key:str|None=_HeaderE(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-CAI-1 — Desktop record_expense (category, reason >= 3, refused on a closed day), in the cashier's open session.
 2026-10-31: an expense is recorded offline and replayed by the device with its Idempotency-Key — a replay after a lost
 answer returns the first expense instead of recording it twice (the cash would be wrong). Without a key: unchanged."""
 need(actor,'finance.cash.expense.create')
 key=(idempotency_key or '').strip()
 if len(key)>180:raise HTTPException(400,'Idempotency-Key trop longue')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   def run():
    out=PostgresCashIntegrityRepository(c).record_expense(actor.school_id,user_id=actor.user_id,membership_id=actor.membership_id,category=b.category,amount=b.amount,currency=b.currency,reason=b.reason,reference=b.reference)
    _audit(c,actor,'RECORD_EXPENSE','CashExpense',out['id'],None,out);return out
   if not key:return run()
   return IdempotentExecutor(PostgresIdempotencyRepository(c)).execute(scope_key=str(actor.school_id),idempotency_key=key,operation='FINANCE_CASH_EXPENSE',
     payload=b.model_dump(mode='json'),school_id=str(actor.school_id),actor_user_id=str(actor.user_id),action=lambda:(201,_jsonable_out(run()))).body
 except (IdempotencyConflict,IdempotencyInProgress) as e:raise HTTPException(409,str(e)) from e
 except ValueError as e:raise HTTPException(409,str(e)) from e
def _jsonable_out(out:dict)->dict:
 return {k:(v if isinstance(v,(int,float,str,bool)) or v is None else str(v)) for k,v in out.items()}

class ReversalBody(BaseModel):
 reversal_type:str=Field(pattern='^(ANNULATION|REMBOURSEMENT)$');reason:str=Field(min_length=3,max_length=500)
@router.post('/payments/{payment_id}/reverse')
def reverse_payment(payment_id:UUID,b:ReversalBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-REV-1 — Desktop reverse_payment as an append-only counter-operation. Own payment in an open session: cashier;
 any other payment or a closed session: superior authority (GESTIONNAIRE)."""
 can_own='finance.payments.reverse' in actor.permissions;can_sup='finance.payments.reverse.supervisor' in actor.permissions
 if not (can_own or can_sup):need(actor,'finance.payments.reverse')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   out=PostgresCashIntegrityRepository(c).reverse_payment(actor.school_id,payment_id,user_id=actor.user_id,membership_id=actor.membership_id,reversal_type=b.reversal_type,reason=b.reason,can_own=can_own,can_supervisor=can_sup)
   old=out.pop('old');_audit(c,actor,f'PAYMENT_{b.reversal_type}','FinancePayment',payment_id,old,{'status':out['status'],'reversal_id':out['id'],'authority':out['authority']},reason=b.reason)
   return out
 except SupervisorRequired as e:raise HTTPException(403,str(e)) from e
 except LookupError as e:raise HTTPException(404,str(e)) from e
 except ValueError as e:raise HTTPException(409,str(e)) from e
 except IntegrityError as e:raise HTTPException(409,"Ce paiement a déjà fait l'objet d'une contre-opération") from e

@router.get('/day')
def school_day(day:str|None=Query(None),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """School cash day (Desktop cash_day_summary): status, totals per currency, operations, closure snapshots."""
 if 'finance.cash.day.close' not in actor.permissions:need(actor,'finance.cash.other.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=_report(c,actor,day)
 r['operations']=_names(services,r['operations']);return r
@router.post('/day/close')
def close_school_day(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-CAI-3/4 — global closure of the school's cash day (Desktop close_cash_day), individual sessions kept."""
 need(actor,'finance.cash.day.close')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   r,changed=PostgresCashIntegrityRepository(c).close_day(actor.school_id,user_id=actor.user_id)
   if changed:_audit(c,actor,'CLOSE_CASH_DAY','CashDay',actor.school_id,None,{'day':r['day'],'totals':r['totals'],'sessions':r['sessions']})
   return {k:v for k,v in r.items() if k!='operations'}
 except ValueError as e:raise HTTPException(409,str(e)) from e
class ReopenBody(BaseModel):reason:str=Field(min_length=5,max_length=500)
@router.post('/day/reopen')
def reopen_school_day(b:ReopenBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-CAI-2 — Desktop reopen_cash_day: today's closed day, explicit reason, audited."""
 need(actor,'finance.cash.reopen')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   r=PostgresCashIntegrityRepository(c).reopen_day(actor.school_id,user_id=actor.user_id,reason=b.reason)
   _audit(c,actor,'REOPEN_CASH_DAY','CashDay',actor.school_id,{'closed':True},{'closed':False,'day':r['day']},reason=b.reason)
   return {k:v for k,v in r.items() if k!='operations'}
 except ValueError as e:raise HTTPException(409,str(e)) from e

@router.get('/day/journal.pdf')
def day_journal_pdf(day:str|None=Query(None),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-DOC-3 — Desktop export_cash_journal_pdf for the school's day."""
 need(actor,'finance.cash.journal.export');need(actor,'finance.cash.other.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=_report(c,actor,day);name=_school_name(c,actor.school_id)
 r['operations']=_names(services,r['operations']);data=cash_journal_pdf(school_name=name,report=r)
 archive_generated_tx(services,actor,data=data,fmt='PDF',required_capability='finance.cash.journal.export',document_code='finance.cash.journal',title=f"Journal de caisse du {r['day']}",file_name=f"journal_caisse_{r['day']}.pdf")
 return _Stream(_BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="journal_caisse_{r["day"]}.pdf"'})
@router.get('/day/report.pdf')
def day_report_pdf(day:str|None=Query(None),preview:bool=Query(False),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-DOC-3 — Daily financial report. Preview is transient; an official generation is archived."""
 need(actor,'finance.reports.daily.generate')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=_report(c,actor,day);name=_school_name(c,actor.school_id)
 r['operations']=_names(services,r['operations'])
 data=daily_report_pdf(school_name=name,report=r)
 if not preview:
  archive_generated_tx(services,actor,data=data,fmt='PDF',required_capability='finance.reports.daily.generate',document_code='finance.reports.daily',title=f"Rapport financier journalier du {r['day']}",file_name=f"rapport_journalier_{r['day']}.pdf")
 return _Stream(_BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="rapport_journalier_{r["day"]}.pdf"','X-EduSync-Preview':'1' if preview else '0'})


# ---------------------------------------------------------------- 2026-10-25 — owner: « voir les caisses passées et exporter la caisse »
# (Desktop CashPage: day by day navigation, journal PDF). A cashier sees and exports HIS sessions; finance.cash.other.read
# extends to every cashier of the school. Read-only: nothing here changes a session.
from edusync.modules.finance_cash.application.documents import session_journal_xlsx as _session_xlsx, sessions_xlsx as _sessions_xlsx


def _period(start, end):
    a, z = _day(start), _day(end)
    z = z or _date.today(); a = a or z.replace(day=1)
    if a > z: raise HTTPException(422, 'La date de début doit précéder la date de fin')
    if (z - a).days > 366: raise HTTPException(422, 'Période trop longue : un an au maximum')
    return a, z


def _cashiers(c, services, sessions):
    """Cashier display name per session: the user who opened it (finance_cash_events OPEN)."""
    ids = [str(x['id']) for x in sessions]
    if not ids: return sessions
    rows = c.execute(text("SELECT DISTINCT ON (cash_session_id) cash_session_id, actor_user_id FROM finance_cash_events WHERE cash_session_id=ANY(CAST(:ids AS uuid[])) AND event_type='OPEN' ORDER BY cash_session_id, created_at"), {'ids': ids}).all()
    opener = {str(r[0]): r[1] for r in rows}
    ops = [{'user_id': opener.get(str(x['id']))} for x in sessions]
    _names(services, ops)
    for x, o in zip(sessions, ops): x['cashier_name'] = o.get('user_name') or '—'
    return sessions


def _list_sessions(c, services, actor, start, end, status, membership_id, limit, offset):
    other = 'finance.cash.other.read' in actor.permissions
    a, z = _period(start, end)
    # Fixed SQL, optional filters as parameters (no interpolated SQL in routes — security audit).
    params = {'sid': str(actor.school_id), 'a': a, 'z': z, 'mid': str(actor.membership_id), 'all': other,
              'st': status if status in ('OPEN', 'CLOSED') else None, 'm': str(membership_id) if (other and membership_id) else None}
    where = """school_id=:sid AND business_date BETWEEN :a AND :z AND (CAST(:all AS boolean) OR membership_id=CAST(:mid AS uuid))
               AND (CAST(:st AS text) IS NULL OR status=CAST(:st AS text)) AND (CAST(:m AS uuid) IS NULL OR membership_id=CAST(:m AS uuid))"""
    total = c.execute(text("SELECT count(*) FROM finance_cash_sessions WHERE " + where), params).scalar_one()
    rows = c.execute(text("SELECT * FROM finance_cash_sessions WHERE " + where + " ORDER BY business_date DESC, opened_at DESC LIMIT :l OFFSET :o"), {**params, 'l': limit, 'o': offset}).mappings().all()
    return a, z, total, _cashiers(c, services, [projection(c, dict(r)) for r in rows])


@router.get('/sessions')
def sessions_history(start: str | None = Query(None), end: str | None = Query(None), status: str | None = Query(None, pattern='^(OPEN|CLOSED)$'),
                     membership_id: UUID | None = None, limit: int = Query(31, ge=1, le=200), offset: int = Query(0, ge=0),
                     actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.cash.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        a, z, total, items = _list_sessions(c, services, actor, start, end, status, membership_id, limit, offset)
    tot = {cur: {k: str(sum((Decimal(x[cur.lower()][k] or 0) for x in items), Decimal('0'))) for k in ('receipts', 'expenses', 'reversals', 'expected_cash')} for cur in ('CDF', 'USD')}
    return {'start': a.isoformat(), 'end': z.isoformat(), 'total': total, 'items': items, 'page_totals': tot, 'all_cashiers': 'finance.cash.other.read' in actor.permissions}


@router.get('/sessions.xlsx')
def sessions_history_xlsx(start: str | None = Query(None), end: str | None = Query(None), status: str | None = Query(None, pattern='^(OPEN|CLOSED)$'),
                          membership_id: UUID | None = None, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.cash.read'); need(actor, 'finance.cash.journal.export')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        a, z, _, items = _list_sessions(c, services, actor, start, end, status, membership_id, 200, 0); name = _school_name(c, actor.school_id)
        data = _sessions_xlsx(school_name=name, start=a.isoformat(), end=z.isoformat(), sessions=items)
    archive_generated_tx(services, actor, data=data, fmt='XLSX', required_capability='finance.cash.journal.export', document_code='finance.cash.sessions',
                         title=f"Historique des caisses du {a} au {z}", file_name=f"caisses_{a}_{z}.xlsx")
    return _Stream(_BytesIO(data), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="caisses_{a}_{z}.xlsx"'})


def _session_export(c, services, actor, session_id):
    r = one(c, 'SELECT * FROM finance_cash_sessions WHERE id=:id AND school_id=:sid', {'id': str(session_id), 'sid': str(actor.school_id)})
    if not r: raise HTTPException(404, 'Caisse introuvable')
    if str(r['membership_id']) != str(actor.membership_id) and 'finance.cash.other.read' not in actor.permissions:
        raise HTTPException(403, 'Cette caisse appartient à un autre caissier')
    session = _cashiers(c, services, [projection(c, r)])[0]
    ops = PostgresCashIntegrityRepository(c).session_operations(actor.school_id, session_id)
    return session, _names(services, ops), _school_name(c, actor.school_id)


@router.get('/{session_id}/journal.pdf')
def session_journal_pdf(session_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.cash.read'); need(actor, 'finance.cash.journal.export')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        session, ops, name = _session_export(c, services, actor, session_id)
    totals = []
    for cur in ('CDF', 'USD'):
        x = session[cur.lower()]; out = Decimal(x['expenses']) + Decimal(x['reversals'])
        if Decimal(x['receipts']) or out or Decimal(x['opening']):
            totals.append({'currency': cur, 'entries': x['receipts'], 'outflows': str(out), 'net': x['expected_cash']})
    day = str(session['business_date'])
    report = {'day': day, 'closed': session['status'] == 'CLOSED', 'totals': totals, 'operations': [{**o, 'user_name': o.get('user_name') or session['cashier_name']} for o in ops]}
    data = cash_journal_pdf(school_name=name, report=report, title=f"JOURNAL DE CAISSE — {session['cashier_name']} — {day}")
    archive_generated_tx(services, actor, data=data, fmt='PDF', required_capability='finance.cash.journal.export', document_code='finance.cash.session_journal',
                         title=f"Journal de caisse de {session['cashier_name']} du {day}", file_name=f"journal_caisse_{day}.pdf")
    return _Stream(_BytesIO(data), media_type='application/pdf', headers={'Content-Disposition': f'inline; filename="journal_caisse_{day}.pdf"'})


@router.get('/{session_id}/journal.xlsx')
def session_journal_xlsx_route(session_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.cash.read'); need(actor, 'finance.cash.journal.export')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        session, ops, name = _session_export(c, services, actor, session_id)
    day = str(session['business_date'])
    data = _session_xlsx(school_name=name, session=session, cashier=session['cashier_name'], operations=ops)
    archive_generated_tx(services, actor, data=data, fmt='XLSX', required_capability='finance.cash.journal.export', document_code='finance.cash.session_journal',
                         title=f"Journal de caisse de {session['cashier_name']} du {day}", file_name=f"journal_caisse_{day}.xlsx")
    return _Stream(_BytesIO(data), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': f'attachment; filename="journal_caisse_{day}.xlsx"'})
