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
@router.post('/collect')
def collect(body:CollectBody,idempotency_key:str|None=Header(None,alias='Idempotency-Key'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.checkout.collect')
 if not idempotency_key:raise HTTPException(400,'Idempotency-Key obligatoire')
 try:
  with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return PostgresFinanceCheckoutRepository(conn).collect(actor.school_id,actor.user_id,actor.membership_id,body.enrollment_id,body.charge_ids,body.amount,body.currency,idempotency_key,body.use_anticipation)
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
 return {**dict(r),'id':str(r['id'])} if r else {'name':'École'}
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
def print_receipt(payment_id:UUID,format:str|None=Query(None,pattern='^(A5|80MM)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.receipts.print')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  repo=PostgresFinanceCheckoutRepository(conn);facts=repo.receipt_facts(actor.school_id,payment_id)
  if not facts:raise HTTPException(404,'Reçu introuvable')
  if repo.receipt_copies(actor.school_id,payment_id)>=1:need(actor,'finance.receipts.reprint')
  copy=repo.record_receipt_print(actor.school_id,payment_id,actor.user_id);_audit_print(conn,actor,payment_id,copy)
  data=receipt_pdf(school=_school_for_receipt(conn,actor.school_id),receipts=[{**_with_cashier(services,facts),'copy_no':copy}],fmt=format or repo.print_settings(actor.school_id)['receipt_format'])
 return Response(data,media_type='application/pdf',headers={**_PDF_HEADERS,'Content-Disposition':f'inline; filename="recu_{facts["receipt_number"]}.pdf"'})
@router.post('/family-baskets/{basket_id}/receipts/print')
def print_basket_receipts(basket_id:UUID,format:str|None=Query(None,pattern='^(A5|80MM)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
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
  data=receipt_pdf(school=_school_for_receipt(conn,actor.school_id),receipts=receipts,fmt=format or repo.print_settings(actor.school_id)['receipt_format'])
 return Response(data,media_type='application/pdf',headers={**_PDF_HEADERS,'Content-Disposition':'inline; filename="recus_panier_familial.pdf"'})
@router.get('/print-settings')
def get_print_settings(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.receipts.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return PostgresFinanceCheckoutRepository(conn).print_settings(actor.school_id)
class PrintSettingsBody(BaseModel):
 receipt_policy:str=Field(pattern='^(NONE|PROPOSE|AUTO_PREVIEW)$');receipt_format:str=Field(pattern='^(A5|80MM)$')
@router.put('/print-settings')
def put_print_settings(body:PrintSettingsBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'settings.documents.manage')
 from sqlalchemy import text as _t
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
  row=conn.execute(_t("""INSERT INTO school_print_settings(school_id,receipt_policy,receipt_format,updated_by) VALUES(:sid,:p,:f,:u)
   ON CONFLICT(school_id) DO UPDATE SET receipt_policy=EXCLUDED.receipt_policy,receipt_format=EXCLUDED.receipt_format,updated_by=EXCLUDED.updated_by,updated_at=now(),version=school_print_settings.version+1
   RETURNING receipt_policy,receipt_format,version"""),{'sid':str(actor.school_id),'p':body.receipt_policy,'f':body.receipt_format,'u':str(actor.user_id)}).mappings().one()
  conn.execute(_t("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,new_json) VALUES(:sid,:uid,:mid,'PRINT_SETTINGS_UPDATED','SchoolPrintSettings',:sid,'WEB',
   jsonb_build_object('receipt_policy',CAST(:p AS text),'receipt_format',CAST(:f AS text)))"""),{'sid':str(actor.school_id),'uid':str(actor.user_id),'mid':str(actor.membership_id),'p':body.receipt_policy,'f':body.receipt_format})
  return dict(row)
