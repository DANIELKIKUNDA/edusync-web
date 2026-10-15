from decimal import Decimal
from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import text
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.modules.finance_controls.domain.models import VALID_RESPONSIBILITIES
router=APIRouter(tags=['Centre financier · Décisions financières'])
def need(a,c):
 try:a.require(c)
 except PermissionError as e:raise HTTPException(403,str(e))
def rows(c,sql,p):return [dict(x) for x in c.execute(text(sql),p).mappings().all()]

@router.get('/decisions')
def decisions(status:str='ACTIVE',actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.decisions.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  return {'items':rows(c,"""SELECT d.*,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student,sc.label class_label,ft.label fee_label FROM finance_decisions d JOIN enrollments e ON e.id=d.enrollment_id JOIN students s ON s.id=e.student_id JOIN school_classes sc ON sc.id=e.class_id LEFT JOIN finance_charges ch ON ch.id=d.charge_id LEFT JOIN fee_types ft ON ft.id=ch.fee_type_id WHERE d.school_id=:s AND (:st='ALL' OR d.status=:st) ORDER BY d.effective_date DESC,d.created_at DESC""",{'s':str(actor.school_id),'st':status})}
from edusync.adapters.postgres_financial_decisions import PostgresFinancialDecisionsRepository
import json as _json
def _audit(c,actor,action,entity_type,entity_id,old,new,reason=None):
 c.execute(text("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,old_json,new_json)
  VALUES(:sid,:uid,:mid,:a,:et,:eid,'WEB',CAST(:o AS jsonb),CAST(:n AS jsonb))"""),{'sid':str(actor.school_id),'uid':str(actor.user_id),'mid':str(actor.membership_id),
  'a':action,'et':entity_type,'eid':str(entity_id),'o':_json.dumps(old,default=str) if old is not None else None,'n':_json.dumps({**(new or {}),**({'reason':reason} if reason else {})},default=str)})
def _plain(v):return _json.loads(_json.dumps(v,default=str))
class DecisionBody(BaseModel):
 """Desktop create_financial_decision (N3-C). decision_type = nature; the former Web field names are kept."""
 enrollment_id:UUID;decision_type:str;scope_type:str='ALL_FEES';scope_ref:str|None=Field(default=None,max_length=80);charge_id:UUID|None=None
 value_type:str|None=None;amount:Decimal=Field(default=Decimal('0'),ge=0,max_digits=18,decimal_places=2);currency:str=Field(default='CDF',pattern='^(CDF|USD)$')
 priority:int=Field(default=100,ge=0,le=10000);cumulative:bool=True;period_start:date|None=None;period_end:date|None=None
 effective_date:date|None=None;effective_to:date|None=None;reason:str=Field(min_length=3,max_length=500);reference:str|None=Field(default=None,max_length=120)
@router.post('/decisions')
def create_decision(b:DecisionBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.decisions.create')
 scope_type,scope_ref=(('CHARGE',str(b.charge_id)) if b.charge_id and b.scope_type in ('ALL_FEES','CHARGE') else (b.scope_type,b.scope_ref))
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   r=PostgresFinancialDecisionsRepository(c).create_decision(actor.school_id,user_id=actor.user_id,enrollment_id=b.enrollment_id,decision_kind=b.decision_type,
     scope_type=scope_type,scope_ref=scope_ref,value_type=b.value_type or ('FIXED' if b.charge_id else 'PERCENT'),value_amount=b.amount,currency=b.currency,priority=b.priority,cumulative=b.cumulative,
     period_start=b.period_start,period_end=b.period_end,effective_from=b.effective_date,effective_to=b.effective_to,reason=b.reason,reference=b.reference)
   _audit(c,actor,'CREATE_FINANCIAL_DECISION','FinancialDecision',r['id'],None,{'enrollment_id':str(b.enrollment_id),'scope':r['scope_type'],'kind':r['decision_type'],'value_type':r['value_type'],'value':str(r['value_amount'])},reason=b.reason)
   return _plain(r)
 except ValueError as e:raise HTTPException(409,str(e)) from e
class CancelBody(BaseModel):reason:str=Field(min_length=3,max_length=500)
@router.post('/decisions/{decision_id}/cancel')
def cancel_decision(decision_id:UUID,b:CancelBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.decisions.cancel')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   r=PostgresFinancialDecisionsRepository(c).cancel_decision(actor.school_id,decision_id,user_id=actor.user_id,reason=b.reason)
   _audit(c,actor,'CANCEL_FINANCIAL_DECISION','FinancialDecision',decision_id,{'status':'ACTIVE'},{'status':'CANCELLED'},reason=b.reason)
   return _plain(r)
 except ValueError as e:raise HTTPException(409,str(e)) from e
@router.post('/enrollments/{enrollment_id}/recalculate')
def recalculate(enrollment_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-DEC-2 — Desktop recalculate_enrollment_financial_decisions."""
 need(actor,'finance.decisions.create')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  return {'applications':PostgresFinancialDecisionsRepository(c).recalculate(actor.school_id,enrollment_id)}
@router.get('/charges/{charge_id}/explanation')
def charge_explanation(charge_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-DEC-3 — Desktop charge_financial_explanation: gross, benefit, decisions applied in order, net, settled, remaining."""
 need(actor,'finance.decisions.read')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   return _plain(PostgresFinancialDecisionsRepository(c).explanation(actor.school_id,charge_id))
 except LookupError as e:raise HTTPException(404,str(e)) from e
@router.get('/students/{student_id}/view')
def operator_view(student_id:UUID,year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-DEC-4 — Desktop student_financial_operator_view (read only, never infers cash)."""
 need(actor,'finance.decisions.read')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   return _plain(PostgresFinancialDecisionsRepository(c).operator_view(actor.school_id,student_id,year_id))
 except LookupError as e:raise HTTPException(404,str(e)) from e
@router.get('/follow-up')
def follow_up(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-DEC-4 — Desktop financial_operator_follow_up (decisions with their applications, planned responsibilities)."""
 need(actor,'finance.decisions.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  return _plain(PostgresFinancialDecisionsRepository(c).follow_up(actor.school_id,year_id))
class ChargeResponsibilityBody(BaseModel):
 responsibility_type:str=Field(pattern='^(FAMILY_CASH|PAYROLL_DEDUCTION|THIRD_PARTY)$');planned_amount:Decimal=Field(gt=0,max_digits=18,decimal_places=2)
 responsible_name:str|None=Field(default=None,max_length=160);reference:str|None=Field(default=None,max_length=120);reason:str=Field(min_length=3,max_length=500)
@router.post('/charges/{charge_id}/responsibility')
def set_charge_responsibility(charge_id:UUID,b:ChargeResponsibilityBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """Desktop set_charge_responsibility: planned settlement of one charge, never above the real remaining."""
 need(actor,'finance.responsibility.set')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   r,old=PostgresFinancialDecisionsRepository(c).set_charge_responsibility(actor.school_id,user_id=actor.user_id,charge_id=charge_id,responsibility_type=b.responsibility_type,
     planned_amount=b.planned_amount,responsible_name=b.responsible_name,reference=b.reference,reason=b.reason)
   _audit(c,actor,'SET_CHARGE_RESPONSIBILITY','ChargeResponsibility',r['id'],_plain(old) if old else None,{'charge_id':str(charge_id),'type':r['responsibility_type'],'planned_amount':str(r['planned_amount'])},reason=b.reason)
   return _plain(r)
 except ValueError as e:raise HTTPException(409,str(e)) from e

@router.get('/responsibilities')
def responsibilities(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.responsibility.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  return {'items':rows(c,"""SELECT DISTINCT ON(r.enrollment_id) r.*,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student,sc.label class_label FROM finance_responsibilities r JOIN enrollments e ON e.id=r.enrollment_id JOIN students s ON s.id=e.student_id JOIN school_classes sc ON sc.id=e.class_id WHERE r.school_id=:s ORDER BY r.enrollment_id,r.effective_from DESC,r.created_at DESC""",{'s':str(actor.school_id)})}
class ResponsibilityBody(BaseModel):
 enrollment_id:UUID;responsibility_mode:str;responsible_label:str|None=Field(default=None,max_length=160);effective_from:date;effective_until:date|None=None;notes:str|None=Field(default=None,max_length=500)
@router.post('/responsibilities')
def set_responsibility(b:ResponsibilityBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.responsibility.set')
 if b.responsibility_mode not in VALID_RESPONSIBILITIES:raise HTTPException(422,'Responsabilité invalide')
 if b.effective_until and b.effective_until<b.effective_from:raise HTTPException(422,'Période invalide')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=c.execute(text("""INSERT INTO finance_responsibilities(school_id,enrollment_id,responsibility_mode,responsible_label,effective_from,effective_until,notes,created_by) VALUES(:s,:e,:m,:l,:f,:t,:n,:u) RETURNING *"""),{'s':str(actor.school_id),'e':str(b.enrollment_id),'m':b.responsibility_mode,'l':b.responsible_label,'f':b.effective_from,'t':b.effective_until,'n':b.notes,'u':str(actor.user_id)}).mappings().first();return dict(r)

@router.get('/credits')
def credits(status:str=Query('OPEN',pattern='^(OPEN|CONSUMED|REFUNDED|CANCELLED|ALL)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.credits.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  return {'items':rows(c,"""SELECT cr.*,cr.original_amount-cr.consumed_amount remaining,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student,sc.label class_label FROM finance_credits cr LEFT JOIN enrollments e ON e.id=cr.enrollment_id LEFT JOIN students s ON s.id=e.student_id LEFT JOIN school_classes sc ON sc.id=e.class_id WHERE cr.school_id=:s AND (:st='ALL' OR cr.status=:st) ORDER BY cr.created_at DESC""",{'s':str(actor.school_id),'st':status}), 'read_only':True}
