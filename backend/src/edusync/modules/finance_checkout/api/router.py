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
