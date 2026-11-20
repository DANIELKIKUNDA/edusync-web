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
# Owner, 2026-11-17: « l'interface ne doit jamais afficher une classe qui n'est pas de son périmètre » — a section-scoped
# actor (préfet, directeur de section, des études, de discipline) sees only the pupils of his classes, unless the role is
# given « toute l'école » in Accès & rôles.
from edusync.adapters.class_scope import visible_class_ids
def scope(c,actor,cap):
 v=visible_class_ids(c.connection.driver_connection,actor.school_id,actor.scopes_for(cap))
 return {'scope_all':v is None,'scope_cids':[str(x) for x in (v or ())]}
def guard_student(c,actor,cap,student_id=None,charge_id=None):
 sc=scope(c,actor,cap)
 if sc['scope_all']:return
 sql=("SELECT 1 FROM enrollments e WHERE e.school_id=:s AND e.student_id=:x AND e.class_id=ANY(CAST(:scope_cids AS uuid[]))" if student_id else
      "SELECT 1 FROM finance_charges fc JOIN enrollments e ON e.id=fc.enrollment_id WHERE fc.school_id=:s AND fc.id=:x AND e.class_id=ANY(CAST(:scope_cids AS uuid[]))")
 if c.execute(text(sql),{'s':str(actor.school_id),'x':str(student_id or charge_id),'scope_cids':sc['scope_cids']}).first() is None:
  raise HTTPException(403,'Cet élève est hors de votre périmètre')

@router.get('/decisions')
def decisions(status:str='ACTIVE',actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.decisions.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  return {'items':rows(c,"""SELECT d.*,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student,sc.label class_label,COALESCE(ft.label,CASE WHEN d.scope_type='FEE_CODE' THEN (SELECT f2.label FROM fee_types f2 WHERE f2.school_id=d.school_id AND upper(f2.code)=upper(d.scope_ref) LIMIT 1) WHEN d.scope_type='FEE_CATEGORY' THEN (SELECT fcat.label FROM fee_categories fcat WHERE fcat.school_id=d.school_id AND upper(fcat.code)=upper(d.scope_ref) LIMIT 1) END) fee_label FROM finance_decisions d JOIN enrollments e ON e.id=d.enrollment_id JOIN students s ON s.id=e.student_id JOIN school_classes sc ON sc.id=e.class_id LEFT JOIN finance_charges ch ON ch.id=d.charge_id LEFT JOIN fee_types ft ON ft.id=ch.fee_type_id WHERE d.school_id=:s AND (:st='ALL' OR d.status=:st) AND (CAST(:scope_all AS boolean) OR e.class_id=ANY(CAST(:scope_cids AS uuid[]))) ORDER BY d.effective_date DESC,d.created_at DESC""",{'s':str(actor.school_id),'st':status,**scope(c,actor,'finance.decisions.read')})}
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
   guard_student(c,actor,'finance.decisions.read',charge_id=charge_id)
   return _plain(PostgresFinancialDecisionsRepository(c).explanation(actor.school_id,charge_id))
 except LookupError as e:raise HTTPException(404,str(e)) from e
@router.get('/students/{student_id}/view')
def operator_view(student_id:UUID,year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-DEC-4 — Desktop student_financial_operator_view (read only, never infers cash)."""
 need(actor,'finance.decisions.read')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
   guard_student(c,actor,'finance.decisions.read',student_id=student_id)
   return _plain(PostgresFinancialDecisionsRepository(c).operator_view(actor.school_id,student_id,year_id))
 except LookupError as e:raise HTTPException(404,str(e)) from e
@router.get('/follow-up')
def follow_up(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """G-DEC-4 — Desktop financial_operator_follow_up (decisions with their applications, planned responsibilities)."""
 need(actor,'finance.decisions.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  return _plain(PostgresFinancialDecisionsRepository(c).follow_up(actor.school_id,year_id,scope(c,actor,'finance.decisions.read')))
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
  return {'items':rows(c,"""SELECT DISTINCT ON(r.enrollment_id) r.*,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student,sc.label class_label FROM finance_responsibilities r JOIN enrollments e ON e.id=r.enrollment_id JOIN students s ON s.id=e.student_id JOIN school_classes sc ON sc.id=e.class_id WHERE r.school_id=:s AND (CAST(:scope_all AS boolean) OR e.class_id=ANY(CAST(:scope_cids AS uuid[]))) ORDER BY r.enrollment_id,r.effective_from DESC,r.created_at DESC""",{'s':str(actor.school_id),**scope(c,actor,'finance.responsibility.read')})}
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
  # N3-D: credits and overpayments are the Desktop « fonds anticipés » (received advances and decision credits).
  st={'OPEN':'ACTIF','CONSUMED':'EPUISE','REFUNDED':'REMBOURSE','CANCELLED':'ANNULE','ALL':'ALL'}[status]
  return {'items':rows(c,"""SELECT f.id,f.enrollment_id,f.currency,f.amount original_amount,f.allocated_amount consumed_amount,f.available_amount remaining,
     f.origin_type origin,f.status,f.receipt_number,f.received_at created_at,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student,sc.label class_label
     FROM finance_advance_fund_state f JOIN enrollments e ON e.id=f.enrollment_id JOIN students s ON s.id=e.student_id JOIN school_classes sc ON sc.id=e.class_id
     WHERE f.school_id=:s AND (:st='ALL' OR f.status=:st) AND (CAST(:scope_all AS boolean) OR e.class_id=ANY(CAST(:scope_cids AS uuid[]))) ORDER BY f.received_at DESC""",{'s':str(actor.school_id),'st':st,**scope(c,actor,'finance.credits.read')}),'read_only':True}


# ---------------------------------------------------------------------- décision groupée (owner, 2026-11-20)
# « Exonérer en une seule passe tous les enfants des agents (par exemple des frais de l'État) » : one traceable decision
# per child and per fee, exactly as if made one by one, after a preview that lists the children and flags those who
# already have the same decision. Covers the whole school year unless a later date is chosen.
from typing import Literal as _Literal


class GroupDecisionBody(BaseModel):
 group: _Literal['STAFF_CHILDREN'] = 'STAFF_CHILDREN'
 decision_type: str = 'EXEMPTION'
 fee_codes: list[str] = Field(min_length=1, max_length=30)
 value_type: _Literal['PERCENT', 'FIXED'] = 'PERCENT'
 amount: Decimal = Field(default=Decimal('100'), ge=0, max_digits=18, decimal_places=2)
 currency: str = Field(default='CDF', pattern='^(CDF|USD)$')
 effective_date: date | None = None
 reason: str = Field(min_length=3, max_length=500)
 execute: bool = False


def _group_targets(c, actor, year_id):
 sc = scope(c, actor, 'finance.decisions.create')
 return rows(c, f"""SELECT DISTINCT e.id AS enrollment_id, concat_ws(' ', s.last_name, s.middle_name, s.first_name) AS student, sc.label AS class_label
   FROM staff_student_links l JOIN students s ON s.id=l.student_id AND s.school_id=l.school_id
   JOIN enrollments e ON e.student_id=s.id AND e.school_id=s.school_id AND e.academic_year_id=:y AND e.status='VALIDATED'
   JOIN school_classes sc ON sc.id=e.class_id
  WHERE l.school_id=:s AND l.active AND (CAST(:scope_all AS boolean) OR e.class_id=ANY(CAST(:scope_cids AS uuid[])))
  ORDER BY student""", {'s': str(actor.school_id), 'y': str(year_id), **sc})


@router.post('/decisions/group')
def group_decision(b: GroupDecisionBody, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
 need(actor, 'finance.decisions.create')
 codes = sorted({x.strip().upper() for x in b.fee_codes if x and x.strip()})
 if not codes: raise HTTPException(422, 'Choisissez au moins un frais')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
  y = c.execute(text("SELECT id, start_date FROM academic_years WHERE school_id=:s ORDER BY (status='ACTIVE') DESC, start_date DESC LIMIT 1"),
                {'s': str(actor.school_id)}).mappings().first()
  if not y: raise HTTPException(409, 'Année scolaire introuvable')
  fees = {r['code']: r['label'] for r in rows(c, "SELECT upper(code) AS code, label FROM fee_types WHERE school_id=:s AND upper(code)=ANY(:c)",
                                               {'s': str(actor.school_id), 'c': codes})}
  missing = [x for x in codes if x not in fees]
  if missing: raise HTTPException(422, 'Frais inconnu : ' + ', '.join(missing))
  start = b.effective_date or y['start_date']
  targets = _group_targets(c, actor, y['id'])
  plan = []
  for t in targets:
   for code in codes:
    dup = c.execute(text("""SELECT 1 FROM finance_decisions WHERE school_id=:s AND enrollment_id=:e AND status='ACTIVE'
        AND scope_type='FEE_CODE' AND upper(scope_ref)=:c LIMIT 1"""), {'s': str(actor.school_id), 'e': str(t['enrollment_id']), 'c': code}).first()
    plan.append({'enrollment_id': str(t['enrollment_id']), 'student': t['student'], 'class_label': t['class_label'], 'fee_code': code,
                 'fee_label': fees[code], 'status': 'ALREADY' if dup else 'NEW'})
  out = {'effective_date': str(start), 'children': len(targets), 'items': plan, 'created': 0}
  if not b.execute:
   return out
  repo = PostgresFinancialDecisionsRepository(c)
  try:
   for p in plan:
    if p['status'] != 'NEW': continue
    r = repo.create_decision(actor.school_id, user_id=actor.user_id, enrollment_id=UUID(p['enrollment_id']), decision_kind=b.decision_type,
                             scope_type='FEE_CODE', scope_ref=p['fee_code'], value_type=b.value_type, value_amount=b.amount, currency=b.currency,
                             effective_from=start, reason=b.reason, reference='Décision groupée — enfants du personnel')
    _audit(c, actor, 'CREATE_FINANCIAL_DECISION', 'FinancialDecision', r['id'], None,
           {'enrollment_id': p['enrollment_id'], 'scope': 'FEE_CODE', 'fee': p['fee_code'], 'kind': r['decision_type'], 'group': b.group}, reason=b.reason)
    out['created'] += 1
  except ValueError as e:
   raise HTTPException(409, f"{p['student']} — {p['fee_label']} : {e}") from e
  return out
