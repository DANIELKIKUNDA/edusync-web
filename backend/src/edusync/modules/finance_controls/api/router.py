from decimal import Decimal
from datetime import date
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import text
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.modules.finance_controls.domain.models import VALID_DECISIONS,VALID_RESPONSIBILITIES
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
class DecisionBody(BaseModel):
 enrollment_id:UUID;charge_id:UUID|None=None;decision_type:str;currency:str=Field(pattern='^(CDF|USD)$');amount:Decimal=Field(ge=0,max_digits=18,decimal_places=2);reason:str=Field(min_length=3,max_length=500);effective_date:date
@router.post('/decisions')
def create_decision(b:DecisionBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.decisions.create')
 if b.decision_type not in VALID_DECISIONS:raise HTTPException(422,'Type de décision invalide')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=c.execute(text("""INSERT INTO finance_decisions(school_id,enrollment_id,charge_id,decision_type,currency,amount,reason,effective_date,created_by) VALUES(:s,:e,:ch,:t,:cur,:a,:r,:d,:u) RETURNING *"""),{'s':str(actor.school_id),'e':str(b.enrollment_id),'ch':str(b.charge_id) if b.charge_id else None,'t':b.decision_type,'cur':b.currency,'a':b.amount,'r':b.reason,'d':b.effective_date,'u':str(actor.user_id)}).mappings().first();return dict(r)
class CancelBody(BaseModel):reason:str=Field(min_length=3,max_length=500)
@router.post('/decisions/{decision_id}/cancel')
def cancel_decision(decision_id:UUID,b:CancelBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.decisions.cancel')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=c.execute(text("UPDATE finance_decisions SET status='CANCELLED',cancelled_by=:u,cancelled_at=now(),cancel_reason=:r WHERE id=:id AND school_id=:s AND status='ACTIVE' RETURNING *"),{'u':str(actor.user_id),'r':b.reason,'id':str(decision_id),'s':str(actor.school_id)}).mappings().first()
  if not r:raise HTTPException(409,'Décision absente ou déjà annulée')
  return dict(r)

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
