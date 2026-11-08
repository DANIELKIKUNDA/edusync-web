from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query
from edusync.bootstrap.dependencies import get_services,require_school_actor
from edusync.bootstrap.services import AppServices
from edusync.shared.application.context import ActorContext
from edusync.adapters.postgres_fee_tracking import PostgresFeeTrackingRepository
router=APIRouter(tags=['finance-fee-tracking'])
def need(a,p):
    try:a.require(p)
    except PermissionError as e:raise HTTPException(403,str(e)) from e
def need_desk_or_analysis(a):
    # Owner, 2026-11-08: the cashier receives the parents every day — the family / pupil sheet shows him the same financial
    # situation as the promoteur. He already reads each child's balance at the desk (finance.checkout.balance.read).
    if not any(c in a.permissions for c in ('finance.analysis.by_fee.read','finance.checkout.balance.read')):need(a,'finance.analysis.by_fee.read')
def repo_call(actor,services,fn):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:return fn(PostgresFeeTrackingRepository(conn))
@router.get('/taxonomy')
def taxonomy(year_id:UUID|None=None,actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.analysis.by_fee.read')
    def f(r):
        y=r.year(actor.school_id,year_id);return {'academic_year':y,'items':r.taxonomy(actor.school_id,y['id']) if y else []}
    return repo_call(actor,services,f)
@router.get('/overview')
def overview(year_id:UUID|None=None,currency:str='CDF',actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.analysis.by_fee.read')
    def f(r):
        y=r.year(actor.school_id,year_id);return {'academic_year':y,'currency':currency,'items':r.overview(actor.school_id,y['id'],currency) if y else []}
    return repo_call(actor,services,f)
@router.get('/students')
def students(year_id:UUID|None=None,currency:str='CDF',fee_type_id:UUID|None=None,category_id:str|None=None,class_id:UUID|None=None,section_id:UUID|None=None,status:str|None=None,q:str|None=Query(None,max_length=80),limit:int=Query(200,ge=1,le=1000),offset:int=Query(0,ge=0),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need(actor,'finance.analysis.by_fee.read')
    def f(r):
        y=r.year(actor.school_id,year_id)
        if not y:return {'academic_year':None,'currency':currency,'items':[],'total':0,'limit':limit,'offset':offset}
        items,total=r.students_page(actor.school_id,y['id'],currency,fee_type_id,category_id,class_id,section_id,status,q=q,limit=limit,offset=offset)
        return {'academic_year':y,'currency':currency,'items':items,'total':total,'totals':r.last_totals,'limit':limit,'offset':offset}
    return repo_call(actor,services,f)
@router.get('/student/{student_id}')
def student(student_id:UUID,currency:str='CDF',actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need_desk_or_analysis(actor);return repo_call(actor,services,lambda r:r.student_summary(actor.school_id,student_id,currency))
@router.get('/family/{family_id}')
def family(family_id:UUID,currency:str='CDF',actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    need_desk_or_analysis(actor);return repo_call(actor,services,lambda r:r.family_summary(actor.school_id,family_id,currency))
