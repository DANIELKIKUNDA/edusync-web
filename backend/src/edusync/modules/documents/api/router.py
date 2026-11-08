from __future__ import annotations
from io import BytesIO
from hashlib import sha256
from fastapi import APIRouter,Depends,HTTPException,Query,Request
from fastapi.responses import Response,StreamingResponse
from edusync.modules.documents.application import object_store
from edusync.shared.infrastructure.object_storage import ObjectStorageError
from edusync.bootstrap.dependencies import require_school_actor,get_services
from edusync.bootstrap.services import AppServices
from sqlalchemy import text
from uuid import UUID
from edusync.shared.application.context import ActorContext
from edusync.modules.documents.domain.catalog import CATALOG, visible_catalog
from edusync.modules.documents.application.templates import student_import_template_xlsx

router=APIRouter(tags=["documents"])
def _need(actor,cap):
    try: actor.require(cap)
    except PermissionError as exc: raise HTTPException(status_code=403,detail=str(exc)) from exc

@router.get("/catalog")
def catalog(actor:ActorContext=Depends(require_school_actor)):
    items=visible_catalog(actor.permissions)
    # Folders of the generated documents (owner, 2026-11-08): every archived document goes to the folder named after its
    # catalog family, even when the reader cannot PRODUCE that document himself (a promoteur reads the pupils' directory
    # archived by the secretariat) — names and folders only, no content, no right granted.
    families=[{"code":d.code,"label":d.label,"module":d.module,"archive_codes":list(d.archive_codes)} for d in CATALOG]
    return {"items":items,"families":families,"canonical_count":16,"visible_count":len(items),"doctrine":"COPIER_COMPARER_CERTIFIER_ENRICHIR"}

@router.get("/student-import-template.xlsx")
def student_import_template(academic_year_id:UUID|None=Query(None),actor:ActorContext=Depends(require_school_actor),services:AppServices=Depends(get_services)):
    _need(actor,"documents.student_import_template.export")
    # Exporting a class template is a data read: never enumerate classes
    # outside the export capability's explicit SECTION/CLASS grants.
    scopes = actor.scopes_for("documents.student_import_template.export")
    schoolwide = any(t == "SCHOOL" for t, _ in scopes)
    sections = sorted({str(v).upper() for t, v in scopes if t == "SECTION" and v})
    class_codes = sorted({str(v).upper() for t, v in scopes if t == "CLASS" and v})
    if not schoolwide and not sections and not class_codes:
        raise HTTPException(403, "Aucune classe autorisée pour cet export")
    classes=[]
    with services.tenant_db.tenant_transaction(school_id=actor.school_id,user_id=actor.user_id) as conn:
        if academic_year_id:
            predicates = ["sc.school_id=:sid", "sc.academic_year_id=:y", "sc.enabled"]
            params = {"sid": actor.school_id, "y": academic_year_id}
            if not schoolwide:
                allowed = []
                if sections:
                    allowed.append("upper(ss.code) IN :sections")
                    params["sections"] = sections
                if class_codes:
                    allowed.append("upper(sc.code) IN :class_codes")
                    params["class_codes"] = class_codes
                predicates.append("(" + " OR ".join(allowed) + ")")
            from sqlalchemy import bindparam
            stmt = text(f"""SELECT sc.code FROM school_classes sc
                JOIN school_sections ss ON ss.id=sc.section_id
                WHERE {' AND '.join(predicates)} ORDER BY sc.code""")
            if sections and not schoolwide:
                stmt = stmt.bindparams(bindparam("sections", expanding=True))
            if class_codes and not schoolwide:
                stmt = stmt.bindparams(bindparam("class_codes", expanding=True))
            classes=[row[0] for row in conn.execute(stmt, params).all()]
    data=student_import_template_xlsx(school_name="EduSync École",classes=classes)
    return StreamingResponse(BytesIO(data),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":'attachment; filename="modele_import_eleves_edusync.xlsx"'})


# --- Object storage: logo, archive, signed links (local closure 2026-10) -----------------------------
_UNAVAILABLE = "Le stockage des documents est momentanément indisponible. Vos données ne sont pas affectées."


def _storage(services: AppServices):
    if services.object_storage is None:
        raise HTTPException(503, _UNAVAILABLE)
    return services.object_storage


@router.get("/storage/status")
def storage_status(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    return {"available": services.object_storage is not None}


@router.put("/branding/logo")
async def upload_logo(request: Request, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "settings.documents.manage")
    data = await request.body()
    try:
        content_type, ext = object_store.validate_logo(data)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    digest = sha256(data).hexdigest()
    key = object_store.logo_key(actor.school_id, digest, ext)
    storage = _storage(services)
    try:
        storage.put(key, data, content_type=content_type, metadata={"school-id": str(actor.school_id), "purpose": "school-logo"})
    except ObjectStorageError as exc:
        raise HTTPException(503, _UNAVAILABLE) from exc
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        old = conn.execute(text("SELECT logo_object_key,logo_sha256,version FROM school_branding WHERE school_id=:s FOR UPDATE"), {"s": str(actor.school_id)}).mappings().first()
        conn.execute(text("""INSERT INTO school_branding(school_id,logo_object_key,logo_content_type,logo_sha256,logo_byte_size,updated_by)
            VALUES(:s,:k,:ct,:h,:n,:u) ON CONFLICT(school_id) DO UPDATE SET logo_object_key=EXCLUDED.logo_object_key,logo_content_type=EXCLUDED.logo_content_type,
            logo_sha256=EXCLUDED.logo_sha256,logo_byte_size=EXCLUDED.logo_byte_size,updated_by=EXCLUDED.updated_by,updated_at=now(),version=school_branding.version+1"""),
            {"s": str(actor.school_id), "k": key, "ct": content_type, "h": digest, "n": len(data), "u": str(actor.user_id)})
        from edusync.adapters.postgres_repositories import PostgresAuditRepository
        from edusync.modules.audit.domain.audit import AuditRecord
        PostgresAuditRepository(conn).append(AuditRecord(action="SCHOOL_LOGO_UPDATED", entity_type="SchoolBranding", entity_id=actor.school_id,
            actor_user_id=actor.user_id, membership_id=actor.membership_id, school_id=actor.school_id, source=actor.source,
            old_data={"sha256": old["logo_sha256"]} if old else None, new_data={"sha256": digest, "bytes": len(data), "content_type": content_type},
            reason=None, correlation_id=actor.correlation_id, idempotency_key=actor.idempotency_key))
    return {"status": "saved", "content_type": content_type, "byte_size": len(data), "sha256": digest}


@router.get("/branding/logo")
def school_logo(actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        row = conn.execute(text("SELECT logo_object_key,logo_content_type,logo_sha256 FROM school_branding WHERE school_id=:s"), {"s": str(actor.school_id)}).mappings().first()
    if not row:
        raise HTTPException(404, "Aucun logo enregistré")
    if not str(row["logo_object_key"]).startswith(f"schools/{actor.school_id}/branding/"):
        raise HTTPException(404, "Aucun logo enregistré")
    try:
        data = _storage(services).get(row["logo_object_key"])
    except ObjectStorageError as exc:
        raise HTTPException(503, _UNAVAILABLE) from exc
    return Response(content=data, media_type=row["logo_content_type"], headers={"Cache-Control": "private, max-age=300", "ETag": f'"{row["logo_sha256"]}"', "X-Content-Type-Options": "nosniff"})


@router.get("/history")
def document_history(offset: int = Query(0, ge=0, le=100_000), limit: int = Query(50, ge=1, le=200),
                     scope: str = Query("school", pattern="^(mine|school)$"),
                     actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "documents.history.read")
    # Archived generations have no persisted section provenance. Do not
    # expose even the creator's archive to a section-only actor: ownership
    # does not prove that its contents belong to the currently granted scope.
    if not any(t == "SCHOOL" for t, _ in actor.scopes_for("documents.history.read")):
        # Fail closed WITHOUT breaking the screen: no archive is listed, and the reason is stated (PR #27; provenance
        # persistence is the open item of the section isolation handoff).
        return {"items": [], "has_more": False, "offset": offset, "limit": limit, "storage_available": True,
                "restricted": "Historique documentaire sans provenance de section vérifiable : les archives de l’école "
                              "ne sont consultables qu’avec un périmètre école. Vos exports restent téléchargeables à leur création."}
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        if scope == "mine":
            rows = conn.execute(text("""SELECT g.id,g.document_code,g.format,g.title,g.byte_size,g.generated_at updated_at,g.file_name,u.full_name generated_by,
                  (SELECT count(*) FROM generated_documents h WHERE h.school_id=g.school_id AND h.logical_key=g.logical_key) generations
                FROM generated_documents g LEFT JOIN users u ON u.id=g.generated_by
                WHERE g.school_id=:s AND g.generated_by=:u
                ORDER BY g.generated_at DESC,g.id LIMIT :l OFFSET :o"""),
                {"s": str(actor.school_id), "u": str(actor.user_id), "l": limit + 1, "o": offset}).mappings().all()
        else:
            rows = conn.execute(text("""SELECT c.latest_generation_id id,c.document_code,c.format,c.title,c.byte_size,c.updated_at,g.file_name,u.full_name generated_by,
                  (SELECT count(*) FROM generated_documents h WHERE h.school_id=c.school_id AND h.logical_key=c.logical_key) generations
                FROM current_documents c JOIN generated_documents g ON g.id=c.latest_generation_id AND g.school_id=c.school_id LEFT JOIN users u ON u.id=c.updated_by
                WHERE c.school_id=:s AND (g.generated_by=:u OR g.required_capability=ANY(CAST(:caps AS text[])))
                ORDER BY c.updated_at DESC,c.logical_key LIMIT :l OFFSET :o"""),
                {"s": str(actor.school_id), "u": str(actor.user_id), "caps": object_store.school_wide_capabilities(actor), "l": limit + 1, "o": offset}).mappings().all()
    items = [dict(r) for r in rows[:limit]]
    return {"items": items, "offset": offset, "limit": limit, "has_more": len(rows) > limit, "storage_available": services.object_storage is not None}


@router.post("/history/{generation_id}/link")
def document_link(generation_id: UUID, actor: ActorContext = Depends(require_school_actor), services: AppServices = Depends(get_services)):
    _need(actor, "documents.open")
    if not any(t == "SCHOOL" for t, _ in actor.scopes_for("documents.open")):
        raise HTTPException(403, "Document sans provenance de section vérifiable")
    with services.tenant_db.tenant_transaction(school_id=actor.school_id, user_id=actor.user_id) as conn:
        found = conn.execute(text("SELECT 1 FROM generated_documents WHERE school_id=:s AND id=:id AND (generated_by=:u OR required_capability=ANY(CAST(:caps AS text[])))"),
                             {"s": str(actor.school_id), "id": str(generation_id), "u": str(actor.user_id), "caps": object_store.school_wide_capabilities(actor)}).first()
    if not found:
        raise HTTPException(404, "Document introuvable")
    token, exp = object_store.sign_link(services.settings, document_id=str(generation_id), school_id=str(actor.school_id), user_id=str(actor.user_id))
    return {"url": f"/api/v1/documents/open?token={token}", "expires_at": exp}


@router.get("/open")
def open_signed_document(token: str = Query(..., min_length=20, max_length=600), services: AppServices = Depends(get_services)):
    """Short-lived signed link (new tab / print). Re-checks membership and tenant ownership before streaming."""
    try:
        claim = object_store.verify_link(services.settings, token)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from exc
    with services.tenant_db.tenant_transaction(school_id=UUID(claim["school_id"]), user_id=UUID(claim["user_id"])) as conn:
        # the account must still be active too (certification 2026-10-30: a disabled account closes its links at once)
        member = conn.execute(text("""SELECT 1 FROM school_memberships m JOIN schools s ON s.id=m.school_id JOIN users u ON u.id=m.user_id
            WHERE m.user_id=:u AND m.school_id=:s AND m.active AND s.status='ACTIVE' AND u.active"""), {"u": claim["user_id"], "s": claim["school_id"]}).first()
        doc = conn.execute(text("SELECT object_key,content_type,file_name,format,generated_by,required_capability FROM generated_documents WHERE school_id=:s AND id=:id"), {"s": claim["school_id"], "id": claim["document_id"]}).mappings().first()
        # Signed URLs cannot outlive membership or permission revocation.
        # Re-evaluate effective RBAC inside the same tenant transaction.
        if not member or not doc:
            raise HTTPException(403, "Lien invalide")
        from edusync.adapters.postgres_repositories import PostgresMembershipRepository
        from edusync.adapters.postgres_authorization import PostgresAuthorizationRepository
        membership = conn.execute(text("SELECT id FROM school_memberships WHERE school_id=:s AND user_id=:u AND active LIMIT 1"),
                                  {"s": claim["school_id"], "u": claim["user_id"]}).first()
        if not membership:
            raise HTTPException(403, "Lien invalide")
        permissions = PostgresMembershipRepository(conn).permissions(membership[0])
        grants = PostgresAuthorizationRepository(conn).effective_capability_grants(UUID(claim["user_id"]), UUID(claim["school_id"]))
        current_actor = ActorContext(user_id=UUID(claim["user_id"]), school_id=UUID(claim["school_id"]),
                                     membership_id=membership[0], permissions=permissions, capability_scopes=grants)
        if "documents.open" not in permissions:
            raise HTTPException(403, "Droit de consultation révoqué")
        if not any(t == "SCHOOL" for t, _ in current_actor.scopes_for("documents.open")):
            raise HTTPException(403, "Document sans provenance de section vérifiable")
        if str(doc["generated_by"]) != claim["user_id"] and doc["required_capability"] not in object_store.school_wide_capabilities(current_actor):
            raise HTTPException(403, "Droit de consultation révoqué")
    if not str(doc["object_key"]).startswith(f"schools/{claim['school_id']}/"):
        raise HTTPException(403, "Lien invalide")
    try:
        data = _storage(services).get(doc["object_key"])
    except ObjectStorageError as exc:
        raise HTTPException(503, _UNAVAILABLE) from exc
    name = object_store.safe_file_name(doc["file_name"] or "document")
    return Response(content=data, media_type=doc["content_type"] or object_store.FORMATS.get(doc["format"], "application/octet-stream"),
                    headers={"Content-Disposition": f'inline; filename="{name}"', "Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
