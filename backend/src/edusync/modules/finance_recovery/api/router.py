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
@router.get('/monthly')
def monthly(year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');y,_,rows,total=load(actor,services,year_id,currency);return {'academic_year':{k:str(v) for k,v in y.items()},'currency':currency,'items':rows,'total':total}
# Existing VF-01 export rights are deliberately reused; no fictitious global export permission is introduced.
@router.get('/monthly.pdf')
def pdf(year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export_pdf');y,s,rows,total=load(actor,services,year_id,currency);data=monthly_pdf(school=s,year_label=y['label'],currency=currency,rows=rows,total=total);return StreamingResponse(BytesIO(data),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="suivi_mensuel_recouvrement.pdf"'})
@router.get('/monthly.xlsx')
def xlsx(year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export_xlsx');y,s,rows,total=load(actor,services,year_id,currency);data=monthly_xlsx(school=s,year_label=y['label'],currency=currency,rows=rows,total=total);return StreamingResponse(BytesIO(data),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="suivi_mensuel_recouvrement.xlsx"'})

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
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export_pdf');y,s,d=_register_load(actor,services,year_id,class_id,currency);return StreamingResponse(BytesIO(class_register_pdf(school=s,year_label=y['label'],data=d)),media_type='application/pdf',headers={'Content-Disposition':'inline; filename="registre_classe.pdf"'})
@router.get('/class-register.xlsx')
def class_register_xlsx_route(class_id:UUID,year_id:UUID|None=None,currency:str=Query('CDF',pattern='^(CDF|USD)$'),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export_xlsx');y,s,d=_register_load(actor,services,year_id,class_id,currency);return StreamingResponse(BytesIO(class_register_xlsx(school=s,year_label=y['label'],data=d)),media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',headers={'Content-Disposition':'attachment; filename="registre_classe.xlsx"'})

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
    need(actor,'finance.recovery.monthly.read');need(actor,'finance.views.vf01.export_pdf' if fmt=='pdf' else 'finance.views.vf01.export_xlsx');y,s,rows,total,title=_summary_load(actor,services,kind,year_id,currency,class_id,section_id,period_order);data=summary_pdf(school=s,title=title,year_label=y['label'],currency=currency,rows=rows,total=total) if fmt=='pdf' else summary_xlsx(school=s,title=title,year_label=y['label'],currency=currency,rows=rows,total=total);return StreamingResponse(BytesIO(data),media_type='application/pdf' if fmt=='pdf' else 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
