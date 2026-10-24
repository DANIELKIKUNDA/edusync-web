from decimal import Decimal
from uuid import UUID
from fastapi import APIRouter,Depends,Header,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy.exc import IntegrityError
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.adapters.postgres_finance_checkout import PostgresFinanceCheckoutRepository
router=APIRouter(tags=['Centre financier · Encaissement'])
def need(a,c):
 try:a.require(c)
 except PermissionError as e:raise HTTPException(403,str(e))
def need_plan_view(a):
 # Desktop applicable_anticipation_plans / anticipation_payment_preview carry no role check: whoever records the parent's
 # decision or collects with a plan at the cash desk sees the applicable plans (no extra right to grant the cashier).
 if not any(c in a.permissions for c in ('finance.anticipation.collect','finance.anticipation_membership.set')):need(a,'finance.anticipation_plans.read')
@router.get('/search')
def search(q:str=Query(...,min_length=1),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.checkout.search')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return {'items':PostgresFinanceCheckoutRepository(conn).search(actor.school_id,q)}
@router.get('/family/{family_id}/children')
def children(family_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.checkout.search')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return {'items':PostgresFinanceCheckoutRepository(conn).family_children(actor.school_id,family_id)}
@router.get('/balance/{enrollment_id}')
def balance(enrollment_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.checkout.balance.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return {'items':PostgresFinanceCheckoutRepository(conn).charges(actor.school_id,enrollment_id)}
def _audit(conn,actor,action,entity_type,entity_id,new):
 import json as _json
 from sqlalchemy import text as _t
 conn.execute(_t("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,new_json)
  VALUES(:sid,:uid,:mid,:a,:et,:eid,'WEB',CAST(:n AS jsonb))"""),{'sid':str(actor.school_id),'uid':str(actor.user_id),'mid':str(actor.membership_id),
  'a':action,'et':entity_type,'eid':str(entity_id),'n':_json.dumps(new,default=str)})

@router.get('/anticipation-plans/{enrollment_id}')
def anticipation_plans_for(enrollment_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 # Desktop applicable_anticipation_plans: active, effective plans whose scope matches the student's class, with membership.
 need_plan_view(actor)
 from edusync.adapters.postgres_anticipation import PostgresAnticipationRepository
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   return {'items':_jsonable_any(PostgresAnticipationRepository(conn).applicable_plans(actor.school_id,enrollment_id))}
 except ValueError as e:raise HTTPException(409,str(e)) from e
class MembershipBody(BaseModel):
 enrollment_id:UUID;status:str=Field(pattern='^(ENROLLED|DECLINED|PAUSED)$');notes:str|None=Field(default=None,max_length=500)
@router.post('/anticipation-plans/{plan_id}/membership')
def anticipation_membership(plan_id:UUID,body:MembershipBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 # Desktop set_anticipation_membership: the parent joins, declines or pauses (installments rebuilt, target frozen).
 need(actor,'finance.anticipation_membership.set')
 from edusync.adapters.postgres_anticipation import PostgresAnticipationRepository
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   out,old=PostgresAnticipationRepository(conn).set_membership(actor.school_id,body.enrollment_id,plan_id,status=body.status,user_id=actor.user_id,notes=body.notes)
   _audit(conn,actor,'ANTICIPATION_MEMBERSHIP_SET','AnticipationMembership',out['id'],{'plan_id':str(plan_id),'enrollment_id':str(body.enrollment_id),
          'status':out['status'],'snapshot_target_amount':str(out['snapshot_target_amount']),'previous':(old or {}).get('status')})
   return _jsonable_any(out)
 except LookupError as e:raise HTTPException(404,str(e)) from e
 except ValueError as e:raise HTTPException(409,str(e)) from e
@router.get('/anticipation-plans/{plan_id}/preview')
def anticipation_preview(plan_id:UUID,enrollment_id:UUID,month:str=Query(...,pattern='^(0[1-9]|1[0-2])$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need_plan_view(actor)
 from edusync.adapters.postgres_anticipation import PostgresAnticipationRepository
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   return _jsonable_any(PostgresAnticipationRepository(conn).preview(actor.school_id,enrollment_id,plan_id,month))
 except LookupError as e:raise HTTPException(404,str(e)) from e
 except ValueError as e:raise HTTPException(409,str(e)) from e
class PlanCollectBody(BaseModel):
 enrollment_id:UUID;plan_id:UUID;contribution_month:str=Field(pattern='^(0[1-9]|1[0-2])$');amount:Decimal=Field(gt=0);currency:str=Field(pattern='^(CDF|USD)$')
 mode:str='CASH';reference:str|None=Field(default=None,max_length=80)
@router.post('/collect-plan')
def collect_plan(body:PlanCollectBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 # Desktop record_monthly_payment_with_anticipation: current month first, then only the plan's target months.
 need(actor,'finance.anticipation.collect')
 if not idempotency_key:raise HTTPException(400,'Idempotency-Key obligatoire')
 from edusync.adapters.postgres_anticipation import PostgresAnticipationRepository
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   out=PostgresAnticipationRepository(conn).collect_with_plan(actor.school_id,user_id=actor.user_id,membership_id=actor.membership_id,enrollment_id=body.enrollment_id,
        plan_id=body.plan_id,contribution_month=body.contribution_month,amount=body.amount,currency=body.currency,idempotency_key=idempotency_key,mode=body.mode,reference=body.reference)
   if not out.get('replayed'):_audit(conn,actor,'ANTICIPATION_PAYMENT_RECORDED','FinancePayment',out['id'],{'plan_id':str(body.plan_id),'contribution_month':body.contribution_month,'amount':out['amount'],'allocations':out['allocations']})
   return out
 except LookupError as e:raise HTTPException(404,str(e)) from e
 except ValueError as e:raise HTTPException(409,str(e)) from e
 except IntegrityError as e:raise HTTPException(409,'Opération refusée : elle violerait une règle financière (montant déjà réglé)') from e
def _jsonable_any(v):
 import json as _json
 return _json.loads(_json.dumps(v,default=str))

@router.get('/payment-options')
def payment_options(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 # The modes the school accepts (Desktop payment policy), shown at the cash desk.
 need(actor,'finance.checkout.collect')
 from edusync.adapters.postgres_settings import PostgresSettingsRepository
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  p=PostgresSettingsRepository(conn).get_payment_policy(actor.school_id)
  return {'accepted_modes':p['accepted_modes'],'partial_payments_enabled':p['partial_payments_enabled'],'partial_min_amount':p['partial_min_amount'],
          'future_charge_payments_enabled':p['future_charge_payments_enabled'],'advance_payments_enabled':p['advance_payments_enabled']}
@router.get('/registration-bundle/{enrollment_id}')
def registration_bundle(enrollment_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 # Desktop registration_bundle_due (parity lot L4): obligations required at enrollment, to settle before other fees.
 need(actor,'finance.checkout.balance.read')
 from edusync.adapters.postgres_fee_schedules import PostgresFeeScheduleRepository
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return PostgresFeeScheduleRepository(conn).registration_bundle_due(actor.school_id,enrollment_id)
@router.get('/anticipation/{enrollment_id}')
def anticipation(enrollment_id:UUID,currency:str=Query(...,pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.anticipation_plans.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  plan=PostgresFinanceCheckoutRepository(conn).anticipation(actor.school_id,enrollment_id,currency)
  return {'available':bool(plan and plan.get('available')),'accepted':bool(plan and plan.get('accepted')),'membership_status':plan.get('membership_status') if plan else None,'plan':plan}
class CollectBody(BaseModel):
 enrollment_id:UUID;charge_ids:list[UUID]=Field(min_length=1);amount:Decimal=Field(gt=0);currency:str;use_anticipation:bool=False
 mode:str='CASH';reference:str|None=Field(default=None,max_length=80)
@router.post('/collect')
def collect(body:CollectBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.checkout.collect')
 if not idempotency_key:raise HTTPException(400,'Idempotency-Key obligatoire')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return PostgresFinanceCheckoutRepository(conn).collect(actor.school_id,actor.user_id,actor.membership_id,body.enrollment_id,body.charge_ids,body.amount,body.currency,idempotency_key,body.use_anticipation,mode=body.mode,reference=body.reference)
 except ValueError as e:raise HTTPException(409,str(e)) from e
 # Database invariants (e.g. received > obligation) are business conflicts, never a 500.
 except IntegrityError as e:raise HTTPException(409,'Opération refusée : elle violerait une règle financière (montant déjà réglé)') from e

class BasketLine(BaseModel):
 enrollment_id:UUID;charge_ids:list[UUID]=Field(min_length=1,max_length=24);amount:Decimal=Field(gt=0,max_digits=18,decimal_places=4);currency:str=Field(pattern='^(CDF|USD)$')
class FamilyBasketBody(BaseModel):
 family_id:UUID;lines:list[BasketLine]=Field(min_length=1,max_length=20)
@router.post('/family-collect')
def family_collect(body:FamilyBasketBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.checkout.family.collect');need(actor,'finance.checkout.collect')
 if not idempotency_key:raise HTTPException(400,'Idempotency-Key obligatoire')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   return PostgresFinanceCheckoutRepository(conn).family_collect(actor.school_id,actor.user_id,actor.membership_id,body.family_id,[l.model_dump() for l in body.lines],idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e)) from e
 except IntegrityError as e:raise HTTPException(409,'Opération refusée : elle violerait une règle financière (montant déjà réglé)') from e
@router.get('/family-baskets/{basket_id}')
def family_basket(basket_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.receipts.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  try:return PostgresFinanceCheckoutRepository(conn).family_basket(actor.school_id,basket_id)
  except Exception as e:raise HTTPException(404,'Panier introuvable') from e
@router.get('/old-debts/{student_id}')
def old_debts(student_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.old_debt.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return {'items':PostgresFinanceCheckoutRepository(conn).historical_debts(actor.school_id,student_id)}
@router.get('/products')
def products(q:str='',actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.products.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return {'items':PostgresFinanceCheckoutRepository(conn).products(actor.school_id,q)}
class ProductSaleBody(BaseModel):
 student_id:UUID|None=None;enrollment_id:UUID|None=None;product_id:UUID;quantity:Decimal=Field(gt=0)
@router.post('/products/sell')
def sell_product(body:ProductSaleBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.products.sale')
 if not idempotency_key:raise HTTPException(400,'Idempotency-Key obligatoire')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return PostgresFinanceCheckoutRepository(conn).sell_product(actor.school_id,actor.user_id,actor.membership_id,body.student_id,body.enrollment_id,body.product_id,body.quantity,idempotency_key)
 except ValueError as e:raise HTTPException(409,str(e)) from e
 # Database invariants (e.g. received > obligation) are business conflicts, never a 500.
 except IntegrityError as e:raise HTTPException(409,'Opération refusée : elle violerait une règle financière (montant déjà réglé)') from e


# --- Receipts: printing is a separate, audited action after the payment commit (Point 5B) -------------
from fastapi.responses import Response
from edusync.modules.finance_checkout.application.receipts import receipt_pdf
_PDF_HEADERS={'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'}
def _school_for_receipt(conn,school_id):
 from sqlalchemy import text as _t
 r=conn.execute(_t("SELECT s.id,s.name,s.phone,s.address,s.city,b.logo_object_key FROM schools s LEFT JOIN school_branding b ON b.school_id=s.id WHERE s.id=:sid"),{'sid':str(school_id)}).mappings().first()
 from edusync.modules.documents.application.identity import apply_document_preferences
 return apply_document_preferences(conn,{**dict(r),'id':str(r['id'])}) if r else {'name':'École'}
def _audit_print(conn,actor,payment_id,copy_no):
 from sqlalchemy import text as _t
 conn.execute(_t("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,new_json)
  VALUES(:sid,:uid,:mid,:a,'FinanceReceipt',:pid,'WEB',jsonb_build_object('copy_no',CAST(:n AS int)))"""),
  {'sid':str(actor.school_id),'uid':str(actor.user_id),'mid':str(actor.membership_id),'a':'FINANCE_RECEIPT_PRINTED' if copy_no==1 else 'FINANCE_RECEIPT_REPRINTED','pid':str(payment_id),'n':copy_no})
def _with_cashier(services,facts):
 """Cashier display name through the platform role (tenant role cannot read other users' rows)."""
 if facts and not facts.get('cashier'):
  from sqlalchemy import text as _t
  with services.platform_db.platform_transaction() as pc:
   facts['cashier']=pc.execute(_t("SELECT full_name FROM users WHERE id=:id"),{'id':str(facts['actor_user_id'])}).scalar_one_or_none()
 return facts
@router.post('/receipts/{payment_id}/print')
def print_receipt(payment_id:UUID,format:str|None=Query(None,pattern='^(A5|80MM|58MM)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.receipts.print')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  repo=PostgresFinanceCheckoutRepository(conn);facts=repo.receipt_facts(actor.school_id,payment_id)
  if not facts:raise HTTPException(404,'Reçu introuvable')
  if repo.receipt_copies(actor.school_id,payment_id)>=1:need(actor,'finance.receipts.reprint')
  copy=repo.record_receipt_print(actor.school_id,payment_id,actor.user_id);_audit_print(conn,actor,payment_id,copy)
  data=receipt_pdf(school=_school_for_receipt(conn,actor.school_id),receipts=[{**_with_cashier(services,facts),'copy_no':copy}],fmt=format or repo.print_settings(actor.school_id)['receipt_format'],copies=repo.print_settings(actor.school_id).get('receipt_copies') or 1)
 return Response(data,media_type='application/pdf',headers={**_PDF_HEADERS,'Content-Disposition':f'inline; filename="recu_{facts["receipt_number"]}.pdf"'})
@router.post('/family-baskets/{basket_id}/receipts/print')
def print_basket_receipts(basket_id:UUID,format:str|None=Query(None,pattern='^(A5|80MM|58MM)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'documents.receipts.bundle.print');need(actor,'finance.receipts.print')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  repo=PostgresFinanceCheckoutRepository(conn)
  try:basket=repo.family_basket(actor.school_id,basket_id)
  except Exception as e:raise HTTPException(404,'Panier introuvable') from e
  receipts=[]
  for line in basket['lines']:
   pid=UUID(line['payment_id'])
   if repo.receipt_copies(actor.school_id,pid)>=1:need(actor,'finance.receipts.reprint')
   copy=repo.record_receipt_print(actor.school_id,pid,actor.user_id);_audit_print(conn,actor,pid,copy)
   receipts.append({**_with_cashier(services,repo.receipt_facts(actor.school_id,pid)),'copy_no':copy})
  data=receipt_pdf(school=_school_for_receipt(conn,actor.school_id),receipts=receipts,fmt=format or repo.print_settings(actor.school_id)['receipt_format'],copies=repo.print_settings(actor.school_id).get('receipt_copies') or 1)
 return Response(data,media_type='application/pdf',headers={**_PDF_HEADERS,'Content-Disposition':'inline; filename="recus_panier_familial.pdf"'})
@router.get('/print-settings')
def get_print_settings(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.receipts.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return PostgresFinanceCheckoutRepository(conn).print_settings(actor.school_id)
class PrintSettingsBody(BaseModel):
 receipt_policy:str=Field(pattern='^(NONE|PROPOSE|AUTO_PREVIEW)$');receipt_format:str=Field(pattern='^(A5|80MM|58MM)$')
 receipt_prefix:str=Field(default='REC',pattern='^[A-Za-z0-9]{1,12}$');receipt_copies:int=Field(default=1,ge=1,le=5)
 report_prefix:str=Field(default='RAP',pattern='^[A-Za-z0-9]{1,12}$')   # N3-G / G-REC-5 (Desktop document settings)
 # Settings parity pass 3: Desktop save_document_settings signatory / show_logo (None keeps the stored value).
 signatory_name:str|None=Field(default=None,max_length=120);signatory_title:str|None=Field(default=None,max_length=120);show_school_logo:bool|None=None
@router.put('/print-settings')
def put_print_settings(body:PrintSettingsBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'settings.documents.manage')
 from sqlalchemy import text as _t
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  cur=PostgresFinanceCheckoutRepository(conn).print_settings(actor.school_id)
  sn=cur.get('signatory_name') if body.signatory_name is None else (body.signatory_name.strip() or None)
  stl=cur.get('signatory_title') if body.signatory_title is None else (body.signatory_title.strip() or None)
  logo=cur.get('show_school_logo',True) if body.show_school_logo is None else body.show_school_logo
  row=conn.execute(_t("""INSERT INTO school_print_settings(school_id,receipt_policy,receipt_format,receipt_prefix,receipt_copies,report_prefix,signatory_name,signatory_title,show_school_logo,updated_by)
   VALUES(:sid,:p,:f,:px,:cp,:rp,:sn,:st,:lg,:u)
   ON CONFLICT(school_id) DO UPDATE SET receipt_policy=EXCLUDED.receipt_policy,receipt_format=EXCLUDED.receipt_format,receipt_prefix=EXCLUDED.receipt_prefix,
   receipt_copies=EXCLUDED.receipt_copies,report_prefix=EXCLUDED.report_prefix,signatory_name=EXCLUDED.signatory_name,signatory_title=EXCLUDED.signatory_title,
   show_school_logo=EXCLUDED.show_school_logo,updated_by=EXCLUDED.updated_by,updated_at=now(),version=school_print_settings.version+1
   RETURNING receipt_policy,receipt_format,receipt_prefix,receipt_copies,report_prefix,signatory_name,signatory_title,show_school_logo,version"""),{'sid':str(actor.school_id),'p':body.receipt_policy,'f':body.receipt_format,'rp':body.report_prefix.upper(),
   'px':body.receipt_prefix.upper(),'cp':body.receipt_copies,'sn':sn,'st':stl,'lg':bool(logo),'u':str(actor.user_id)}).mappings().one()
  conn.execute(_t("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,new_json) VALUES(:sid,:uid,:mid,'PRINT_SETTINGS_UPDATED','SchoolPrintSettings',:sid,'WEB',
   jsonb_build_object('receipt_policy',CAST(:p AS text),'receipt_format',CAST(:f AS text),'receipt_prefix',CAST(:px AS text),'receipt_copies',CAST(:cp AS integer)))"""),{'sid':str(actor.school_id),'uid':str(actor.user_id),'mid':str(actor.membership_id),'p':body.receipt_policy,'f':body.receipt_format,'px':body.receipt_prefix.upper(),'cp':body.receipt_copies})
  return dict(row)

# ---------------------------------------------------------------- N3-D — fonds anticipés (Desktop operations.py:290-470)
# Plan anticipé ≠ fonds anticipé: these routes never read nor write the payment plans.
from edusync.adapters.postgres_advance_funds import PostgresAdvanceFundsRepository
from edusync.modules.finance_cash.application.documents import advance_receipt_pdf
class AdvanceFundBody(BaseModel):
 enrollment_id:UUID;amount:Decimal=Field(gt=0,max_digits=18,decimal_places=2);currency:str=Field(pattern='^(CDF|USD)$')
 mode:str='CASH';reference:str|None=Field(default=None,max_length=120)
@router.post('/advance-funds',status_code=201)
def receive_advance_fund(b:AdvanceFundBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """Desktop receive_advance_fund: money received before imputation, own receipt, cashier's open session."""
 need(actor,'finance.advance_funds.receive')
 if not idempotency_key:raise HTTPException(400,'Idempotency-Key obligatoire')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   out=PostgresAdvanceFundsRepository(conn).receive(actor.school_id,user_id=actor.user_id,membership_id=actor.membership_id,enrollment_id=b.enrollment_id,amount=b.amount,currency=b.currency,mode=b.mode,reference=b.reference,idempotency_key=idempotency_key)
   if not out.get('replayed'):_audit(conn,actor,'RECEIVE_ADVANCE_FUND','AdvanceFund',out['id'],{'enrollment_id':str(b.enrollment_id),'amount':str(out['amount']),'currency':out['currency'],'receipt_number':out['receipt_number']})
   return _jsonable_any(out)
 except ValueError as e:raise HTTPException(409,str(e)) from e
@router.get('/advance-funds')
def list_advance_funds(enrollment_id:UUID|None=None,student_id:UUID|None=None,include_closed:bool=True,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.advance_funds.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  return {'items':_jsonable_any(PostgresAdvanceFundsRepository(conn).list(actor.school_id,enrollment_id=enrollment_id,student_id=student_id,include_closed=include_closed))}
class AllocateBody(BaseModel):amount:Decimal|None=Field(default=None,gt=0,max_digits=18,decimal_places=2)
@router.post('/advance-funds/{fund_id}/allocate')
def allocate_advance_fund(fund_id:UUID,b:AllocateBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """Desktop allocate_advance_fund: oldest payable charges of the same currency first."""
 need(actor,'finance.advance_funds.allocate')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   out=PostgresAdvanceFundsRepository(conn).allocate(actor.school_id,fund_id,user_id=actor.user_id,amount=b.amount)
   _audit(conn,actor,'ALLOCATE_ADVANCE_FUND','AdvanceFund',fund_id,{'applied':out['applied'],'available_amount':out['available_amount'],'allocations':out['allocations'],'previous_available':out.pop('old_available')})
   return out
 except LookupError as e:raise HTTPException(404,str(e)) from e
 except ValueError as e:raise HTTPException(409,str(e)) from e
 except IntegrityError as e:raise HTTPException(409,'Opération refusée : elle violerait une règle financière (montant déjà réglé)') from e
class FundCloseBody(BaseModel):reversal_type:str=Field(pattern='^(ANNULATION|REMBOURSEMENT)$');reason:str=Field(min_length=3,max_length=500)
@router.post('/advance-funds/{fund_id}/close')
def close_advance_fund(fund_id:UUID,b:FundCloseBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """Desktop reverse_advance_fund — superior authority (GESTIONNAIRE, owner decision 2026-10-15)."""
 need(actor,'finance.advance_funds.refund')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   out=PostgresAdvanceFundsRepository(conn).close(actor.school_id,fund_id,user_id=actor.user_id,reversal_type=b.reversal_type,reason=b.reason)
   _audit(conn,actor,f'ADVANCE_FUND_{b.reversal_type}','AdvanceFund',fund_id,{'status':out['status'],'previous':out.pop('old_status'),'reason':b.reason})
   return _jsonable_any(out)
 except LookupError as e:raise HTTPException(404,str(e)) from e
 except ValueError as e:raise HTTPException(409,str(e)) from e
@router.get('/advance-funds/{fund_id}/receipt.pdf')
def advance_fund_receipt(fund_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.advance_funds.receipt.print')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   f=PostgresAdvanceFundsRepository(conn).fund(actor.school_id,fund_id);school=_school_for_receipt(conn,actor.school_id)
 except LookupError as e:raise HTTPException(404,str(e)) from e
 if f.get('origin_type')!='PAYMENT_ADVANCE':raise HTTPException(409,'Un crédit issu d’une décision n’a pas de reçu de caisse')
 if f.get('received_by'):
  from sqlalchemy import text as _t
  with services.platform_db.platform_transaction() as pc:f['cashier']=pc.execute(_t("SELECT full_name FROM users WHERE id=:id"),{'id':str(f['received_by'])}).scalar_one_or_none()
 return Response(advance_receipt_pdf(school=school,fund=f),media_type='application/pdf',headers={'Content-Disposition':f'inline; filename="fonds_anticipe_{f.get("receipt_number")}.pdf"'})

# ---------------------------------------------------------------- N3-E — guidance (Desktop recommended_checkout, suggest_checkout_allocations, fee bundles)
from edusync.adapters.postgres_finance_checkout import CheckoutGuidance
@router.get('/recommended/{enrollment_id}')
def recommended_checkout(enrollment_id:UUID,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """Admission bundle first, then the oldest charge due today; nothing future is anticipated silently."""
 need(actor,'finance.checkout.balance.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  return _jsonable_any(CheckoutGuidance(conn).recommended(actor.school_id,enrollment_id))
@router.get('/suggest/{enrollment_id}')
def suggest_allocations(enrollment_id:UUID,amount:Decimal=Query(...,gt=0),currency:str=Query(...,pattern='^(CDF|USD)$'),include_future:bool=False,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.checkout.balance.read')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
   return {'allocations':CheckoutGuidance(conn).suggest(actor.school_id,enrollment_id,amount,currency,include_future=include_future)}
 except ValueError as e:raise HTTPException(409,str(e)) from e
@router.get('/fee-bundle/{enrollment_id}')
def fee_bundle(enrollment_id:UUID,codes:str=Query('JOURNAL_CLASSE,ECUSSON',max_length=300),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 """Desktop fee_bundle_due (default: journal de classe + écusson); paid through the normal collect with these charges."""
 need(actor,'finance.checkout.balance.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  return _jsonable_any(CheckoutGuidance(conn).fee_bundle(actor.school_id,enrollment_id,codes.split(',')))
