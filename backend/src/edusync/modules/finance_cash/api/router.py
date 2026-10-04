from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import text
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
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
 receipts,expenses=totals(conn,row['id']); out=dict(row)
 for cur in ('CDF','USD'):
  opening=Decimal(str(row.get('opening_'+cur.lower()) or 0)); inc=Decimal(receipts.get(cur,'0')); ex=Decimal(expenses.get(cur,'0')); expected=opening+inc-ex
  out[cur.lower()]={'opening':str(opening),'receipts':str(inc),'expenses':str(ex),'expected_cash':str(expected),'counted':str(row.get('counted_'+cur.lower())) if row.get('counted_'+cur.lower()) is not None else None,'variance':str(Decimal(str(row.get('counted_'+cur.lower())))-expected) if row.get('counted_'+cur.lower()) is not None else None}
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
    for field in ('opening','receipts','expenses','expected_cash'):totals[cur][field]+=Decimal(item[key][field])
  return {'business_date':day,'open_count':sum(1 for x in projected if x['status']=='OPEN'),'closed_count':sum(1 for x in projected if x['status']=='CLOSED'),'currencies':{cur:{k:str(v) for k,v in vals.items()} for cur,vals in totals.items()},'sessions':projected}

@router.get('/{session_id}/journal')
def journal(session_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.cash.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=one(c,'SELECT * FROM finance_cash_sessions WHERE id=:id AND school_id=:sid',{'id':str(session_id),'sid':str(actor.school_id)})
  if not r:raise HTTPException(404,'Caisse introuvable')
  if str(r['membership_id'])!=str(actor.membership_id) and 'finance.cash.other.read' not in actor.permissions:raise HTTPException(403,'Cette caisse appartient à un autre caissier')
  items=c.execute(text("""SELECT p.created_at,'RECEIPT' kind,p.receipt_number reference,p.amount,p.currency FROM finance_payments p WHERE p.cash_session_id=:id UNION ALL SELECT e.created_at,'EXPENSE',e.label,e.amount,e.currency FROM finance_cash_expenses e WHERE e.cash_session_id=:id ORDER BY created_at"""),{'id':str(session_id)}).mappings().all()
  return {'session':projection(c,r),'items':[dict(x) for x in items]}
