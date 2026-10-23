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
  rows=c.execute(text("""SELECT COALESCE(ft.label,ch.label,'Autres encaissements') category,COALESCE(sum(COALESCE(pa.amount,fp.amount)),0) amount,count(DISTINCT fp.id) operations FROM finance_payments fp JOIN finance_cash_sessions cs ON cs.id=fp.cash_session_id LEFT JOIN finance_payment_allocations pa ON pa.payment_id=fp.id LEFT JOIN finance_charges ch ON ch.id=pa.charge_id LEFT JOIN fee_types ft ON ft.id=ch.fee_type_id WHERE fp.school_id=:s AND fp.currency=:cur AND fp.created_at::date BETWEEN :a AND :b AND NOT EXISTS (SELECT 1 FROM finance_payment_reversals rv WHERE rv.payment_id=fp.id)"""+where+" GROUP BY 1 ORDER BY 1"),p).mappings().all()
  total=sum((Decimal(str(x['amount'])) for x in rows),Decimal('0'))
 return {'template':dict(tpl),'period':{'start':str(a),'end':str(b)},'currency':currency,'items':[dict(x) for x in rows],'total':str(total),'doctrine':'date_encaissement_preserve_annee_origine_obligation'}

# ---------------------------------------------------------------- N3-G — Desktop periodic reports and analyses
from io import BytesIO as _BytesIO
from uuid import UUID as _UUID
from fastapi.responses import StreamingResponse as _Stream
from edusync.adapters.postgres_periodic_reports import PostgresPeriodicReportsRepository
from edusync.modules.finance_reports.application.documents import periodic_report_pdf, periodic_report_xlsx, student_account_pdf
from edusync.modules.finance_reports.domain.periodic import PERIOD_LABELS, REPORT_PROFILES, periodic_title
from edusync.modules.documents.application.object_store import archive_generated_tx


def _school(c, sid):
    r = c.execute(text("SELECT s.id,s.name,s.phone,s.address,s.city,b.logo_object_key FROM schools s LEFT JOIN school_branding b ON b.school_id=s.id WHERE s.id=:s"), {'s': str(sid)}).mappings().first()
    return {**dict(r), 'id': str(r['id'])} if r else {'name': 'École'}


def _jsonable(v):
    import json as _json
    return _json.loads(_json.dumps(v, default=str))


@router.get('/profiles')
def report_profiles(actor: ActorContext = Depends(require_school_actor)):
    need(actor, 'finance.reports.periodic.generate')
    return {'profiles': [{'code': k, **{x: (list(y) if isinstance(y, tuple) else y) for x, y in v.items()}} for k, v in REPORT_PROFILES.items()],
            'period_types': [{'code': k, 'label': v} for k, v in PERIOD_LABELS.items()]}


def _period(period_type, start, end):
    if period_type not in PERIOD_LABELS:
        raise HTTPException(422, 'Type de période invalide')
    if not start or not end:
        raise HTTPException(422, 'Dates de début et de fin obligatoires')
    return start, end


@router.get('/periodic')
def periodic(profile_code: str = 'CONSOLIDE', period_type: str = 'JOURNALIER', start: date | None = None, end: date | None = None,
             actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Desktop financial_report_rows: rows per payment, deposits presented per the payment policy, FC / USD apart."""
    need(actor, 'finance.reports.periodic.generate'); a, b = _period(period_type, start, end)
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            return _jsonable(PostgresPeriodicReportsRepository(c).report_rows(actor.school_id, start_date=a, end_date=b, profile_code=profile_code))
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


class PeriodicPdfBody(BaseModel):
    profile_code: str = 'CONSOLIDE'
    period_type: str = 'JOURNALIER'
    start: date
    end: date


@router.post('/periodic/pdf')
def periodic_pdf(b: PeriodicPdfBody, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Desktop export_periodic_financial_report_pdf: official PDF, consumes the next report number (PREFIX-NNN)."""
    need(actor, 'finance.reports.periodic.generate'); a, z = _period(b.period_type, b.start, b.end)
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            repo = PostgresPeriodicReportsRepository(c)
            report = repo.report_rows(actor.school_id, start_date=a, end_date=z, profile_code=b.profile_code)
            issued = repo.register(actor.school_id, user_id=actor.user_id, profile_code=b.profile_code, period_type=b.period_type, start_date=a, end_date=z, report=report)
            c.execute(text("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,new_json)
                VALUES(:s,:u,:m,'GENERATE_PERIODIC_REPORT','GeneratedReport',:id,'WEB',
                jsonb_build_object('report',CAST(:l AS text),'profile',CAST(:p AS text),'period',CAST(:t AS text),'start',CAST(:a AS text),'end',CAST(:z AS text)))"""),
                {'s': str(actor.school_id), 'u': str(actor.user_id), 'm': str(actor.membership_id), 'id': issued['id'], 'l': issued['label'], 'p': b.profile_code,
                 't': b.period_type, 'a': str(a), 'z': str(z)})
            school = _school(c, actor.school_id)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    data = periodic_report_pdf(school=school, report=report, period_type=b.period_type, report_label=issued['label'])
    name = f"rapport_{issued['label']}.pdf"
    archive_generated_tx(services, actor, data=data, fmt='PDF', required_capability='finance.reports.periodic.generate', document_code=f'finance.reports.periodic.{b.profile_code}',
                         title=f"{periodic_title(report['profile'], b.period_type)} · {issued['label']}", file_name=name)
    from fastapi.responses import Response as _Response   # a POST answer is sent whole (no streaming through the mutation middleware)
    return _Response(content=data, media_type='application/pdf', headers={'Content-Disposition': f'inline; filename="{name}"', 'X-Report-Number': issued['label']})


@router.get('/periodic.xlsx')
def periodic_xlsx(profile_code: str = 'CONSOLIDE', period_type: str = 'JOURNALIER', start: date | None = None, end: date | None = None,
                  actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Desktop export_periodic_financial_report_xlsx: Excel companion, never consumes an official number."""
    need(actor, 'finance.reports.periodic.export'); a, z = _period(period_type, start, end)
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            report = PostgresPeriodicReportsRepository(c).report_rows(actor.school_id, start_date=a, end_date=z, profile_code=profile_code)
            school = _school(c, actor.school_id)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    return _Stream(_BytesIO(periodic_report_xlsx(school=school, report=report, period_type=period_type)),
                   media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers={'Content-Disposition': 'attachment; filename="rapport_periodique.xlsx"'})


@router.get('/generated')
def generated_reports(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.reports.history.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        return {'items': _jsonable(PostgresPeriodicReportsRepository(c).generated(actor.school_id))}


@router.get('/analysis/fees')
def analysis_fees(year_id: _UUID | None = None, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.analysis.by_fee.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        return {'items': _jsonable(PostgresPeriodicReportsRepository(c).analysis_by_fee_type(actor.school_id, year_id))}


@router.get('/analysis/cashiers')
def analysis_cashiers(year_id: _UUID | None = None, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.analysis.by_cashier.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        items = PostgresPeriodicReportsRepository(c).analysis_by_cashier(actor.school_id, year_id)
    ids = list({i['cashier_id'] for i in items})
    if ids:
        with services.platform_db.platform_transaction() as pc:
            names = {str(r[0]): r[1] for r in pc.execute(text("SELECT id,full_name FROM users WHERE id=ANY(CAST(:ids AS uuid[]))"), {'ids': ids}).all()}
        for i in items:
            i['cashier_name'] = names.get(i['cashier_id']) or 'Utilisateur inconnu'
    return {'items': _jsonable(items)}


@router.get('/analysis/advance-funds')
def analysis_advance_funds(year_id: _UUID | None = None, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.analysis.advance.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        return {'items': _jsonable(PostgresPeriodicReportsRepository(c).analysis_advance_funds(actor.school_id, year_id))}


@router.get('/historical-status')
def historical_status(currency: str = Query('CDF', pattern='^(CDF|USD)$'), year_id: _UUID | None = None,
                      actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Desktop historical_recovery_status: makes an empty recovery view actionable (ready / to verify / posted)."""
    need(actor, 'finance.recovery.monthly.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
        return PostgresPeriodicReportsRepository(c).historical_recovery_status(actor.school_id, year_id=year_id, currency=currency)


@router.get('/students/{student_id}/account')
def student_account(student_id: _UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'students.account.read')
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            return _jsonable(PostgresPeriodicReportsRepository(c).student_account(actor.school_id, student_id))
    except LookupError as e:
        raise HTTPException(404, str(e)) from e


@router.get('/students/{student_id}/account.pdf')
def student_account_pdf_route(student_id: _UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """G-DOC-2 — Desktop export_student_account_pdf."""
    need(actor, 'students.account.export')
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            acc = PostgresPeriodicReportsRepository(c).student_account(actor.school_id, student_id)
            school = _school(c, actor.school_id)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    data = student_account_pdf(school=school, account=acc)
    mat = acc['student'].get('matricule') or 'eleve'
    archive_generated_tx(services, actor, data=data, fmt='PDF', required_capability='students.account.export', document_code='students.account',
                         title=f"Relevé du compte élève {mat}", file_name=f"releve_{mat}.pdf")
    return _Stream(_BytesIO(data), media_type='application/pdf', headers={'Content-Disposition': 'inline; filename="releve_compte_eleve.pdf"'})


@router.get('/product-sales')
def product_sales(start: date, end: date, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """N3-H / G-ART-1 — Desktop product_sales_report: sales of the period, cashier, totals per currency (reversed sales flagged)."""
    need(actor, 'finance.products.sales_report.read')
    from edusync.adapters.postgres_schooling_parity import PostgresSchoolingParityRepository
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            out = PostgresSchoolingParityRepository(c).product_sales_report(actor.school_id, start_date=start, end_date=end)
    except ValueError as e:
        raise HTTPException(409, str(e)) from e
    ids = list({r['cashier_id'] for r in out['rows'] if r.get('cashier_id')})
    if ids:
        with services.platform_db.platform_transaction() as pc:
            names = {str(r[0]): r[1] for r in pc.execute(text("SELECT id,full_name FROM users WHERE id=ANY(CAST(:ids AS uuid[]))"), {'ids': ids}).all()}
        for r in out['rows']:
            r['cashier_name'] = names.get(str(r.get('cashier_id'))) or '—'
    return _jsonable(out)
