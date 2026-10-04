from __future__ import annotations
from io import BytesIO
from fastapi import APIRouter,Depends,HTTPException,Query
from fastapi.responses import StreamingResponse
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from sqlalchemy import text
from uuid import UUID
from edusync.shared.application.context import ActorContext
from edusync.modules.documents.domain.catalog import visible_catalog
from edusync.modules.documents.application.templates import student_import_template_xlsx

router=APIRouter(tags=["documents"])
def _need(actor,cap):
    try: actor.require(cap)
    except PermissionError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc

@router.get("/catalog")
def catalog(actor:ActorContext=Depends(require_school_actor)):
    items=visible_catalog(actor.permissions)
    return {"items":items,"canonical_count":16,"visible_count":len(items),"doctrine":"COPIER_COMPARER_CERTIFIER_ENRICHIR"}

@router.get("/student-import-template.xlsx")
def student_import_template(academic_year_id:UUID|None=Query(None),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"documents.student_import_template.export")
    classes=[]
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        if academic_year_id:
            classes=[r[0] for r in conn.execute(text("SELECT code FROM school_classes WHERE school_id=:sid AND academic_year_id=:y AND enabled ORDER BY code"),{"sid":actor.school_id,"y":academic_year_id}).all()]
    data=student_import_template_xlsx(school_name="EduSync École",classes=classes)
    return StreamingResponse(BytesIO(data),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":'attachment; filename="modele_import_eleves_edusync.xlsx"'})
