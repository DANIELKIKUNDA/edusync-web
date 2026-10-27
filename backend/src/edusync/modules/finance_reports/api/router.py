from decimal import Decimal
from datetime import date
from fastapi import APIRouter,Depends,Header,HTTPException,Query
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
 # This router's periodic/analysis/account repositories currently accept school_id,
 # not the actor's section scopes. A section-bound grant must NEVER silently
 # become school-wide access. Fail closed until each query supports section filters.
 if c.startswith('finance.') or c.startswith('students.account.'):
  scopes=a.scopes_for(c)
  if not any(scope_type=='SCHOOL' for scope_type,_ in scopes):
   raise HTTPException(403,'Rapport financier indisponible pour ce périmètre de section')


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
from edusync.modules.documents.application.object_store import archive_official_pdf_strict,read_official_pdf,discard_official_pdf


def _school(c, sid):
    r = c.execute(text("SELECT s.id,s.name,s.phone,s.address,s.city,b.logo_object_key FROM schools s LEFT JOIN school_branding b ON b.school_id=s.id WHERE s.id=:s"), {'s': str(sid)}).mappings().first()
    from edusync.modules.documents.application.identity import apply_document_preferences   # motto, signatory, logo choice
    return apply_document_preferences(c, {**dict(r), 'id': str(r['id'])}) if r else {'name': 'École'}


def _jsonable(v):
    import json as _json
    return _json.loads(_json.dumps(v, default=str))


@router.get('/profiles')
def report_profiles(actor: ActorContext = Depends(require_school_actor)):
    need(actor, 'finance.reports.periodic.generate')
    return {'profiles': [{'code': k, **{x: (list(y) if isinstance(y, tuple) else y) for x, y in v.items()}} for k, v in REPORT_PROFILES.items() if k in {'CONSOLIDE','FRAIS_SCOLAIRES','ARTICLES_SCOLAIRES'}],
            'period_types': [{'code': k, 'label': v} for k, v in PERIOD_LABELS.items()]}


def _period(period_type, start, end):
    if period_type not in PERIOD_LABELS:
        raise HTTPException(422, 'Type de période invalide')
    if not start or not end:
        raise HTTPException(422, 'Dates de début et de fin obligatoires')
    return start, end


def _need_periodic_scope(actor):
    """Periodic preview is section-aware; official issued reports remain school-wide."""
    try:
        actor.require('finance.reports.periodic.generate')
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    if not actor.scopes_for('finance.reports.periodic.generate'):
        raise HTTPException(403, 'Aucun périmètre financier autorisé')


@router.get('/periodic')
def periodic(profile_code: str = 'CONSOLIDE', period_type: str = 'JOURNALIER', start: date | None = None, end: date | None = None,
             actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Desktop financial_report_rows: rows per payment, deposits presented per the payment policy, FC / USD apart."""
    _need_periodic_scope(actor)
    a, b = _period(period_type, start, end)
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            return _jsonable(PostgresPeriodicReportsRepository(c).report_rows(actor.school_id, start_date=a, end_date=b, profile_code=profile_code, scopes=actor.scopes_for('finance.reports.periodic.generate')))
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


class PeriodicPdfBody(BaseModel):
    profile_code: str = 'CONSOLIDE'
    period_type: str = 'JOURNALIER'
    start: date
    end: date


@router.post('/periodic/pdf')
def periodic_pdf(b: PeriodicPdfBody, idempotency_key: str = Header(..., alias='Idempotency-Key'),
                 actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    """Issue one numbered, archived PDF. Replays return the exact same bytes and number."""
    import re
    from fastapi.responses import Response as _Response
    from edusync.shared.infrastructure.object_storage import ObjectStorageError
    need(actor, 'finance.reports.periodic.generate')
    a, z = _period(b.period_type, b.start, b.end)
    if not re.fullmatch(r'[A-Za-z0-9_-]{20,160}', idempotency_key):
        raise HTTPException(400, 'Idempotency-Key invalide')
    object_key = None
    replayed = False
    try:
        with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as c:
            c.execute(text('SELECT pg_advisory_xact_lock(hashtextextended(:k,0))'),
                      {'k': f'official-report:{actor.school_id}:{idempotency_key}'})
            prior = c.execute(text("""SELECT r.report_label,r.profile_code,r.period_type,r.start_date,r.end_date,r.generated_by,
                    r.document_generation_id,g.object_key
                    FROM finance_generated_reports r LEFT JOIN generated_documents g ON g.id=r.document_generation_id
                    WHERE r.school_id=:s AND r.request_key=:k"""),
                    {'s': str(actor.school_id), 'k': idempotency_key}).mappings().first()
            if prior:
                if (prior['profile_code'] != b.profile_code or prior['period_type'] != b.period_type
                    or prior['start_date'] != a or prior['end_date'] != z
                    or str(prior['generated_by']) != str(actor.user_id)):
                    raise HTTPException(409, 'Clé déjà utilisée pour un autre rapport')
                if not prior['document_generation_id'] or not prior['object_key']:
                    raise HTTPException(409, 'Rapport officiel incomplet : contactez un administrateur')
                data = read_official_pdf(prior['object_key'], actor.school_id)
                label = prior['report_label']; replayed = True
            else:
                repo = PostgresPeriodicReportsRepository(c)
                report = repo.report_rows(actor.school_id, start_date=a, end_date=z, profile_code=b.profile_code)
                issued = repo.register(actor.school_id, user_id=actor.user_id, profile_code=b.profile_code,
                                       period_type=b.period_type, start_date=a, end_date=z, report=report,
                                       request_key=idempotency_key)
                school = _school(c, actor.school_id)
                label = issued['label']
                data = periodic_report_pdf(school=school, report=report, period_type=b.period_type, report_label=label)
                name = f"rapport_{label}.pdf"
                generation_id, object_key = archive_official_pdf_strict(c, actor, data=data,
                    document_code=f'finance.reports.periodic.{b.profile_code}',
                    title=f"{periodic_title(report['profile'], b.period_type)} · {label}", file_name=name,
                    required_capability='finance.reports.periodic.generate')
                c.execute(text('UPDATE finance_generated_reports SET document_generation_id=:g WHERE school_id=:s AND id=:id'),
                          {'g': generation_id, 's': str(actor.school_id), 'id': issued['id']})
                c.execute(text("""INSERT INTO audit_events(school_id,actor_user_id,membership_id,action,entity_type,entity_id,source,new_json)
                    VALUES(:s,:u,:m,'GENERATE_PERIODIC_REPORT','GeneratedReport',:id,'WEB',
                    jsonb_build_object('report',CAST(:l AS text),'profile',CAST(:p AS text),'period',CAST(:t AS text),
                    'start',CAST(:a AS text),'end',CAST(:z AS text)))"""),
                    {'s': str(actor.school_id), 'u': str(actor.user_id), 'm': str(actor.membership_id),
                     'id': issued['id'], 'l': label, 'p': b.profile_code, 't': b.period_type, 'a': str(a), 'z': str(z)})
    except ValueError as e:
        if object_key: discard_official_pdf(object_key)
        raise HTTPException(409, str(e)) from e
    except ObjectStorageError as e:
        if object_key: discard_official_pdf(object_key)
        raise HTTPException(503, 'Archivage du rapport officiel indisponible : aucun numéro émis') from e
    except Exception:
        if object_key: discard_official_pdf(object_key)
        raise
    name = f"rapport_{label}.pdf"
    return _Response(content=data, media_type='application/pdf',
                     headers={'Content-Disposition': f'inline; filename="{name}"',
                              'X-Report-Number': label, 'X-Report-Replayed': 'yes' if replayed else 'no',
                              'Cache-Control': 'private, no-store'})


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
