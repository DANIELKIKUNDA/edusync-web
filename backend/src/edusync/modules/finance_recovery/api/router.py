from __future__ import annotations
from io import BytesIO
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import StreamingResponse
from edusync.bootstrap.dependencies import get_services,require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.adapters.postgres_finance_recovery import PostgresFinanceRecoveryRepository
from edusync.modules.finance_recovery.domain.monthly import monthly_total
from edusync.modules.finance_recovery.application.documents import monthly_pdf,monthly_xlsx
router=APIRouter(tags=['Recouvrement'])
def need(a,c):
    try:a.require(c)
    except PermissionError as e:raise HTTPException(403,str(e)) from e
def load(actor,services,year_id,currency):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresFinanceRecoveryRepository(conn);y=repo.year(actor.school_id,year_id)
        if not y:raise HTTPException(409,'Année scolaire introuvable')
        scopes=actor.scopes_for('finance.recovery.monthly.read'); rows=repo.monthly(actor.school_id,y['id'],currency,scopes=scopes);return y,repo.school_identity(actor.school_id),rows,monthly_total(rows)
from edusync.modules.documents.application.object_store import archive_generated_tx
@router.get('/monthly')
def monthly(year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');y,_,rows,total=load(actor,services,year_id,currency);return {'academic_year':{k:str(v) for k,v in y.items()},'currency':currency,'items':rows,'total':total}
# Existing VF-01 export rights are deliberately reused; no fictitious global export permission is introduced.
@router.get('/monthly.pdf')
def pdf(year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export');y,s,rows,total=load(actor,services,year_id,currency);data=monthly_pdf(school=s,year_label=y['label'],currency=currency,rows=rows,total=total);archive_generated_tx(services,actor,data=data,fmt='PDF',required_capability='finance.recovery.monthly.read',document_code=f'finance.recovery.monthly.{currency}',title=f'Suivi mensuel du recouvrement ({"FC" if currency=="CDF" else currency})',file_name=f'suivi_mensuel_recouvrement_{currency}.pdf',academic_year_id=y['id']);return StreamingResponse(BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="suivi_mensuel_recouvrement.pdf"'})
@router.get('/monthly.xlsx')
def xlsx(year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export');y,s,rows,total=load(actor,services,year_id,currency);data=monthly_xlsx(school=s,year_label=y['label'],currency=currency,rows=rows,total=total);archive_generated_tx(services,actor,data=data,fmt='XLSX',required_capability='finance.recovery.monthly.read',document_code=f'finance.recovery.monthly.{currency}',title=f'Suivi mensuel du recouvrement ({"FC" if currency=="CDF" else currency})',file_name=f'suivi_mensuel_recouvrement_{currency}.xlsx',academic_year_id=y['id']);return StreamingResponse(BytesIO(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="suivi_mensuel_recouvrement.xlsx"'})

from edusync.modules.finance_recovery.application.documents import class_register_pdf,class_register_xlsx
@router.get('/classes')
def recovery_classes(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresFinanceRecoveryRepository(conn);y=repo.year(actor.school_id,year_id)
        if not y:raise HTTPException(409,'Année scolaire introuvable')
        return {'academic_year':{'id':str(y['id']),'label':y['label']},'items':repo.classes(actor.school_id,y['id'])}
def _register_load(actor,services,year_id,class_id,currency):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresFinanceRecoveryRepository(conn);y=repo.year(actor.school_id,year_id)
        if not y:raise HTTPException(409,'Année scolaire introuvable')
        d=repo.class_register(actor.school_id,y['id'],class_id,currency)
        if not d:raise HTTPException(404,'Classe introuvable')
        return y,repo.school_identity(actor.school_id),d
@router.get('/class-register')
def class_register(class_id:UUID,year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');y,_,d=_register_load(actor,services,year_id,class_id,currency);return {'academic_year':{'id':str(y['id']),'label':y['label']},**d}
@router.get('/class-register.pdf')
def class_register_pdf_route(class_id:UUID,year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export');y,s,d=_register_load(actor,services,year_id,class_id,currency);data=class_register_pdf(school=s,year_label=y['label'],data=d);archive_generated_tx(services,actor,data=data,fmt='PDF',required_capability='finance.recovery.monthly.read',document_code=f'finance.recovery.class_register.{class_id}.{currency}',title=f'Registre de classe ({currency})',file_name=f'registre_classe_{currency}.pdf',academic_year_id=y['id']);return StreamingResponse(BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="registre_classe.pdf"'})
@router.get('/class-register.xlsx')
def class_register_xlsx_route(class_id:UUID,year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export');y,s,d=_register_load(actor,services,year_id,class_id,currency);data=class_register_xlsx(school=s,year_label=y['label'],data=d);archive_generated_tx(services,actor,data=data,fmt='XLSX',required_capability='finance.recovery.monthly.read',document_code=f'finance.recovery.class_register.{class_id}.{currency}',title=f'Registre de classe ({currency})',file_name=f'registre_classe_{currency}.xlsx',academic_year_id=y['id']);return StreamingResponse(BytesIO(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="registre_classe.xlsx"'})

from edusync.modules.finance_recovery.domain.summaries import total_row
from edusync.modules.finance_recovery.application.documents import summary_pdf,summary_xlsx
@router.get('/sections')
def sections(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read')
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresFinanceRecoveryRepository(conn);y=repo.year(actor.school_id,year_id);return {'items':repo.section_list(actor.school_id,y['id'])}

def _summary_load(actor,services,kind,year_id,currency,class_id=None,section_id=None,period_order=None):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresFinanceRecoveryRepository(conn);y=repo.year(actor.school_id,year_id);school=repo.school_identity(actor.school_id)
        if kind=='class':
            rows=repo.class_monthly(actor.school_id,y['id'],class_id,currency); rows=[{'label':r['month_label'],**r} for r in rows]; total=total_row(rows,sum_counts=False); title='SYNTHÈSE MENSUELLE PAR CLASSE'
        elif kind=='section':
            rows=repo.scope_summary(actor.school_id,y['id'],currency,section_id,period_order);rows=[{'label':r['class_label'],**r} for r in rows];total=total_row(rows, sum_counts=True);title=('SYNTHÈSE MENSUELLE DE LA SECTION' if period_order is not None else 'SYNTHÈSE DE LA SECTION')
        else:
            raw=repo.scope_summary(actor.school_id,y['id'],currency,period_order=period_order); groups={}
            for r in raw:
                g=groups.setdefault(str(r['section_id']),{'label':r['section_label'],'debtors':0,'in_order':0,'not_in_order':0,'expected':0,'cash_collected':0,'outside_cash':0,'regularized_total':0,'remaining':0})
                for k in ('debtors','in_order','not_in_order','expected','cash_collected','outside_cash','regularized_total','remaining'):g[k]+=r[k] or 0
            rows=list(groups.values())
            for r in rows:r['recovery_rate']=0 if not r['expected'] else round(r['regularized_total']*100/r['expected'],1)
            total=total_row(rows, sum_counts=True);title=("SYNTHÈSE MENSUELLE GLOBALE DE L'ÉCOLE" if period_order is not None else "SYNTHÈSE GLOBALE DE L'ÉCOLE")
        return y,school,rows,total,title
@router.get('/summary/{kind}')
def summary(kind:str,year_id:UUID|None=None,class_id:UUID|None=None,section_id:UUID|None=None,period_order:int|None=Query(None,ge=1,le=12),currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');y,_,rows,total,title=_summary_load(actor,services,kind,year_id,currency,class_id,section_id,period_order);return {'academic_year':{'id':str(y['id']),'label':y['label']},'title':title,'items':rows,'total':total,'currency':currency}
@router.get('/summary/{kind}.{fmt}')
def summary_export(kind:str,fmt:str,year_id:UUID|None=None,class_id:UUID|None=None,section_id:UUID|None=None,period_order:int|None=Query(None,ge=1,le=12),currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export');y,s,rows,total,title=_summary_load(actor,services,kind,year_id,currency,class_id,section_id,period_order);data=summary_pdf(school=s,title=title,year_label=y['label'],currency=currency,rows=rows,total=total) if fmt=='pdf' else summary_xlsx(school=s,title=title,year_label=y['label'],currency=currency,rows=rows,total=total);archive_generated_tx(services,actor,data=data,fmt='PDF' if fmt=='pdf' else 'XLSX',required_capability='finance.recovery.monthly.read',document_code=f'finance.recovery.summary.{kind}.{currency}',title=title.capitalize(),file_name=f'synthese_{kind}_{currency}.{fmt}',academic_year_id=y['id']);return StreamingResponse(BytesIO(data),media_type='application/pdf' if fmt=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ---------------------------------------------------------------- 2026-10-25 — Suivi financier d'un frais (en ordre / non en ordre)
from edusync.modules.finance_recovery.domain.followup import class_followup as _followup, default_column as _default_column, fee_groups as _fee_groups
from edusync.modules.finance_recovery.application.documents import followup_pdf as _followup_pdf, followup_xlsx as _followup_xlsx


def _followup_load(actor, services, class_id, year_id, currency, column, cumulative):
    y, school, reg = _register_load(actor, services, year_id, class_id, currency)
    col = column or _default_column(reg)
    if not col:
        return y, school, {"class_label": reg["class_label"], "currency": currency, "fees": [], "data": None}
    try:
        data = _followup(reg, col, cumulative)
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    return y, school, {"class_label": reg["class_label"], "currency": currency, "fees": _fee_groups(reg["columns"]), "data": data}


@router.get('/followup')
def followup(class_id: UUID, column: str | None = Query(None, max_length=200), cumulative: bool = True, year_id: UUID | None = None,
             currency: str = Query('CDF', pattern='^(CDF|USD)$'), actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    need(actor, 'finance.recovery.monthly.read')
    y, _, out = _followup_load(actor, services, class_id, year_id, currency, column, cumulative)
    return {'academic_year': {'id': str(y['id']), 'label': y['label']}, **out}


@router.get('/followup.{fmt}')
def followup_export(fmt: str, class_id: UUID, column: str | None = Query(None, max_length=200), cumulative: bool = True, all_students: bool = False,
                    year_id: UUID | None = None, currency: str = Query('CDF', pattern='^(CDF|USD)$'),
                    actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    if fmt not in ('pdf', 'xlsx'): raise HTTPException(404, 'Format inconnu')
    need(actor, 'finance.recovery.monthly.read'); need(actor, 'finance.views.vf01.export')
    y, school, out = _followup_load(actor, services, class_id, year_id, currency, column, cumulative)
    if not out['data']: raise HTTPException(409, 'Aucun frais généré pour cette classe')
    d = out['data']; name = f"suivi_{(d['class_label'] or 'classe').replace(' ', '_')}_{d['period_label'].replace(' ', '_')}"
    if fmt == 'pdf':
        data = _followup_pdf(school=school, year_label=y['label'], data=d, only_not_in_order=not all_students); media = 'application/pdf'
    else:
        data = _followup_xlsx(school=school, year_label=y['label'], data=d); media = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    archive_generated_tx(services, actor, data=data, fmt=fmt.upper(), required_capability='finance.views.vf01.export', document_code='finance.recovery.followup',
                         title=f"Suivi financier {d['class_label']} — {d['title']}", file_name=f"{name}.{fmt}")
    return StreamingResponse(BytesIO(data), media_type=media, headers={'Content-Disposition': f'{"inline" if fmt == "pdf" else "attachment"}; filename="{name}.{fmt}"'})


# ------------------------------------------------------------------ executive money view (owner, 2026-11-08)
# « Le tableau de bord du promoteur : l'argent — aujourd'hui, la semaine, le mois, depuis la rentrée — et le reste à recouvrer. »
# Net cash actually received by the school's cash desks: receipts + advance funds, minus cancellations / refunds (in a
# session or by a supervisor), counted by business date. Same definition as the day summary of the cash desks.
PILOTAGE_SQL = """
WITH b AS (SELECT CAST(%(today)s AS date) d, date_trunc('week', CAST(%(today)s AS date))::date w,
                  date_trunc('month', CAST(%(today)s AS date))::date m, CAST(%(start)s AS date) y),
mv AS (
  SELECT s.business_date AS bday, p.currency, p.amount FROM finance_payments p JOIN finance_cash_sessions s ON s.id=p.cash_session_id
   WHERE s.school_id=%(sid)s AND s.business_date >= (SELECT least(y, w) FROM b)
  UNION ALL
  SELECT s.business_date, f.currency, f.amount FROM finance_advance_funds f JOIN finance_cash_sessions s ON s.id=f.cash_session_id
   WHERE s.school_id=%(sid)s AND s.business_date >= (SELECT least(y, w) FROM b)
  UNION ALL
  SELECT r.business_date, r.currency, -r.amount FROM finance_payment_reversals r
   WHERE r.school_id=%(sid)s AND r.business_date >= (SELECT least(y, w) FROM b)
  UNION ALL
  SELECT c.business_date, f.currency, -c.amount FROM finance_advance_fund_closures c JOIN finance_advance_funds f ON f.id=c.fund_id
   WHERE c.school_id=%(sid)s AND c.business_date >= (SELECT least(y, w) FROM b) AND c.closure_type IN ('ANNULATION','REMBOURSEMENT'))
SELECT mv.currency,
       COALESCE(sum(amount) FILTER (WHERE bday = b.d),0) AS today,
       COALESCE(sum(amount) FILTER (WHERE bday >= b.w AND bday <= b.d),0) AS week,
       COALESCE(sum(amount) FILTER (WHERE bday >= b.m AND bday <= b.d),0) AS month,
       COALESCE(sum(amount) FILTER (WHERE bday >= b.y AND bday <= b.d),0) AS year
  FROM mv, b GROUP BY mv.currency"""


@router.get('/pilotage')
def pilotage(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.cash.other.read');need(actor,'finance.recovery.monthly.read')
    from datetime import date as _d
    from psycopg.rows import dict_row as _dr
    today=_d.today()
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        repo=PostgresFinanceRecoveryRepository(conn);y=repo.year(actor.school_id,year_id)
        if not y:raise HTTPException(409,'Année scolaire introuvable')
        start=min(y['start_date'],today)
        with repo.conn.cursor(row_factory=_dr) as c:
            c.execute(PILOTAGE_SQL,{'sid':actor.school_id,'today':today,'start':start});rows={r['currency']:r for r in c.fetchall()}
        cash={cur:{k:str(rows.get(cur,{}).get(k,0) or 0) for k in ('today','week','month','year')} for cur in ('CDF','USD')}
        scopes=actor.scopes_for('finance.recovery.monthly.read');recovery={}
        for cur in ('CDF','USD'):
            items=repo.monthly(actor.school_id,y['id'],cur,scopes=scopes);t=monthly_total(items)
            recovery[cur]={'expected':str(t['expected']),'regularized':str(t['regularized_total']),'remaining':str(t['remaining']),'rate':str(t['recovery_rate'])}
    return {'academic_year':{'id':str(y['id']),'label':y['label'],'start_date':str(y['start_date'])},'today':str(today),
            'week_start':str(today.fromordinal(today.toordinal()-today.weekday())),'month_start':str(today.replace(day=1)),'cash':cash,'recovery':recovery}
