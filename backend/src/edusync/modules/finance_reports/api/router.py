from decimal import Decimal
from datetime import date
from fastapi import APIRouter,Depends,HTTPException,Query
from pydantic import BaseModel,Field
from sqlalchemy import text
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.modules.finance_reports.domain.models import SYSTEM_TEMPLATES,period_bounds,validate_sections
router=APIRouter(tags=['Centre financier · Rapports'])
def need(a,c):
 try:a.require(c)
 except PermissionError as e:raise HTTPException(403,str(e))

def system_templates():return [dict(x,system_template=True,enabled=True) for x in SYSTEM_TEMPLATES]
@router.get('/templates')
def templates(actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.reports.history.read')
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  custom=[dict(x) for x in c.execute(text("SELECT id,code,label,description,scope_mode,sections,system_template,enabled FROM finance_report_templates WHERE school_id=:s AND enabled ORDER BY label"),{'s':str(actor.school_id)}).mappings().all()]
 return {'items':system_templates()+custom}
class TemplateBody(BaseModel):
 code:str=Field(min_length=2,max_length=50,pattern=r'^[A-Z0-9_]+$');label:str=Field(min_length=3,max_length=120);description:str|None=Field(default=None,max_length=300);scope_mode:str='MY_CASH';sections:list[str]
@router.post('/templates')
def create_template(b:TemplateBody,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.reports.periodic.generate')
 if b.scope_mode not in {'MY_CASH','ONE_CASHIER','ALL_CASHIERS'}:raise HTTPException(422,'Périmètre invalide')
 try:sections=validate_sections(b.sections)
 except ValueError as e:raise HTTPException(422,str(e))
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  r=c.execute(text("INSERT INTO finance_report_templates(school_id,code,label,description,scope_mode,sections) VALUES(:s,:c,:l,:d,:m,CAST(:j AS jsonb)) RETURNING id,code,label,description,scope_mode,sections,system_template,enabled"),{'s':str(actor.school_id),'c':b.code,'l':b.label,'d':b.description,'m':b.scope_mode,'j':__import__('json').dumps(sections)}).mappings().first();return dict(r)
@router.get('/preview')
def preview(template_code:str,period:str='TODAY',start:date|None=None,end:date|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
 need(actor,'finance.reports.periodic.generate')
 try:a,b=period_bounds(period,date.today(),start,end)
 except ValueError as e:raise HTTPException(422,str(e))
 sys=next((x for x in SYSTEM_TEMPLATES if x['code']==template_code),None)
 with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as c:
  tpl=sys or c.execute(text("SELECT code,label,scope_mode,sections FROM finance_report_templates WHERE school_id=:s AND code=:c AND enabled"),{'s':str(actor.school_id),'c':template_code}).mappings().first()
  if not tpl:raise HTTPException(404,'Modèle de rapport introuvable')
  scope=tpl['scope_mode'];all_cash=scope=='ALL_CASHIERS'
  if all_cash and 'finance.cash.other.read' not in actor.permissions:raise HTTPException(403,'La consolidation de plusieurs caisses exige un droit de contrôle')
  where='' if all_cash else ' AND cs.membership_id=:mid'
  p={'s':str(actor.school_id),'a':a,'b':b,'cur':currency,'mid':str(actor.membership_id)}
  rows=c.execute(text("""SELECT COALESCE(ft.label,ch.label,'Autres encaissements') category,COALESCE(sum(fp.amount),0) amount,count(*) operations FROM finance_payments fp JOIN finance_cash_sessions cs ON cs.id=fp.cash_session_id LEFT JOIN finance_payment_allocations pa ON pa.payment_id=fp.id LEFT JOIN finance_charges ch ON ch.id=pa.charge_id LEFT JOIN fee_types ft ON ft.id=ch.fee_type_id WHERE fp.school_id=:s AND fp.currency=:cur AND fp.created_at::date BETWEEN :a AND :b"""+where+" GROUP BY 1 ORDER BY 1"),p).mappings().all()
  total=sum((Decimal(str(x['amount'])) for x in rows),Decimal('0'))
 return {'template':dict(tpl),'period':{'start':str(a),'end':str(b)},'currency':currency,'items':[dict(x) for x in rows],'total':str(total),'doctrine':'date_encaissement_preserve_annee_origine_obligation'}
