from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from edusync.modules.personnel.domain.models import StaffAssignment, StaffFunction, StaffMember, StaffSummary
from edusync.shared.domain.concurrency import OptimisticConcurrencyError


def _row(row) -> dict[str, Any]:
    return dict(row._mapping)


def _scope_where(scopes: tuple[tuple[str, str | None], ...], *, alias: str = "sm") -> tuple[str, dict[str, Any]]:
    """SQL visibility rule for personnel identities.

    SCHOOL means full school. SECTION sees personnel assigned to that section
    (including its classes). CLASS sees personnel assigned to that class.
    A school-wide staff assignment must not implicitly widen section access.
    No effective scope fails closed.
    """
    if any(t == "SCHOOL" for t, _ in scopes):
        return "TRUE", {}
    sections = sorted({str(v).upper() for t, v in scopes if t == "SECTION" and v})
    classes = sorted({str(v).upper() for t, v in scopes if t == "CLASS" and v})
    if not sections and not classes:
        return "FALSE", {}
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if sections:
        clauses.append("(sa.scope_type='SECTION' AND upper(sa.scope_value) IN :scope_sections)")
        clauses.append("(sa.scope_type='CLASS' AND EXISTS (SELECT 1 FROM school_classes sc JOIN school_sections ss ON ss.id=sc.section_id WHERE sc.id=sa.class_id AND upper(ss.code) IN :scope_sections))")
        params["scope_sections"] = sections
    if classes:
        clauses.append("(sa.scope_type='CLASS' AND upper(sa.scope_value) IN :scope_classes)")
        params["scope_classes"] = classes
    return f"EXISTS (SELECT 1 FROM staff_assignments sa WHERE sa.school_id={alias}.school_id AND sa.staff_id={alias}.id AND sa.end_date IS NULL AND ({' OR '.join(clauses)}))", params


def _bind_scope(stmt, params: dict[str, Any]):
    if "scope_sections" in params:
        stmt = stmt.bindparams(bindparam("scope_sections", expanding=True))
    if "scope_classes" in params:
        stmt = stmt.bindparams(bindparam("scope_classes", expanding=True))
    return stmt


@dataclass(slots=True)
class PostgresPersonnelRepository:
    connection: Connection

    def _visible_staff_ids(self, school_id: UUID, scopes: tuple[tuple[str, str | None], ...]) -> set[UUID] | None:
        if any(t == "SCHOOL" for t, _ in scopes):
            return None
        where, params = _scope_where(scopes)
        stmt = _bind_scope(text(f"SELECT sm.id FROM staff_members sm WHERE sm.school_id=:sid AND {where}"), params)
        rows = self.connection.execute(stmt, {"sid": school_id, **params}).all()
        return {r[0] for r in rows}

    def list_staff(self, school_id: UUID, *, query: str | None = None, status: str | None = None,
                   category: str | None = None, scopes: tuple[tuple[str, str | None], ...] = (),
                   limit: int = 500, offset: int = 0) -> list[dict[str, Any]]:
        where_scope, params = _scope_where(scopes)
        conditions = ["sm.school_id=:sid", where_scope]
        args: dict[str, Any] = {"sid": school_id, **params}
        if query and query.strip():
            conditions.append("(sm.employee_no ILIKE :q OR sm.last_name ILIKE :q OR coalesce(sm.first_name,'') ILIKE :q OR coalesce(sm.middle_name,'') ILIKE :q OR coalesce(sm.phone,'') ILIKE :q)")
            args["q"] = f"%{query.strip()}%"
        if status:
            conditions.append("sm.status=:status")
            args["status"] = status
        if category:
            conditions.append("sm.category=:category")
            args["category"] = category
        stmt = text(f"""
            SELECT sm.*,
              (SELECT count(*) FROM staff_assignments a WHERE a.school_id=sm.school_id AND a.staff_id=sm.id AND a.end_date IS NULL) AS active_assignment_count,
              EXISTS(SELECT 1 FROM staff_access_links l WHERE l.school_id=sm.school_id AND l.staff_id=sm.id AND l.active) AS has_linked_access,
              (SELECT count(*) FROM staff_student_links sl WHERE sl.school_id=sm.school_id AND sl.staff_id=sm.id AND sl.active) AS staff_children_count,
              coalesce((SELECT jsonb_agg(jsonb_build_object(
                 'id',a.id,'function_id',a.function_id,'function_code',f.code,'function_label',f.label,
                 'scope_type',a.scope_type,'scope_value',a.scope_value,'is_primary',a.is_primary,
                 'is_titular',a.is_titular,'titular_class_id',a.titular_class_id,'start_date',a.start_date,
                 'end_date',a.end_date,'version',a.version
               ) ORDER BY a.is_primary DESC,f.sort_order,f.label)
               FROM staff_assignments a JOIN staff_functions f ON f.id=a.function_id
              WHERE a.school_id=sm.school_id AND a.staff_id=sm.id AND a.end_date IS NULL), '[]'::jsonb) AS assignments
            FROM staff_members sm
            WHERE {' AND '.join(conditions)}
            ORDER BY CASE sm.status WHEN 'ACTIVE' THEN 0 WHEN 'SUSPENDED' THEN 1 WHEN 'INACTIVE' THEN 2 ELSE 3 END,
                     sm.last_name,sm.middle_name NULLS LAST,sm.first_name NULLS LAST
            LIMIT :limit OFFSET :offset
        """)
        stmt = _bind_scope(stmt, params)
        args["limit"]=max(1,min(int(limit),1000));args["offset"]=max(0,int(offset))
        return [_row(r) for r in self.connection.execute(stmt, args).all()]

    def count_staff(self, school_id: UUID, *, query: str | None = None, status: str | None = None, category: str | None = None, scopes: tuple[tuple[str,str|None], ...] = ()) -> int:
        where_scope,params=_scope_where(scopes);conditions=["sm.school_id=:sid",where_scope];args:dict[str,Any]={"sid":school_id,**params}
        if query and query.strip(): conditions.append("(sm.employee_no ILIKE :q OR sm.last_name ILIKE :q OR coalesce(sm.first_name,'') ILIKE :q OR coalesce(sm.middle_name,'') ILIKE :q OR coalesce(sm.phone,'') ILIKE :q)");args["q"]=f"%{query.strip()}%"
        if status: conditions.append("sm.status=:status");args["status"]=status
        if category: conditions.append("sm.category=:category");args["category"]=category
        stmt=_bind_scope(text(f"SELECT count(*) FROM staff_members sm WHERE {' AND '.join(conditions)}"),params)
        return int(self.connection.execute(stmt,args).scalar_one())

    def get_staff(self, school_id: UUID, staff_id: UUID, *, scopes: tuple[tuple[str, str | None], ...] = (("SCHOOL", None),)) -> dict[str, Any] | None:
        visible = self._visible_staff_ids(school_id, scopes)
        if visible is not None and staff_id not in visible:
            return None
        row = self.connection.execute(text("SELECT * FROM staff_members WHERE school_id=:sid AND id=:id"), {"sid":school_id,"id":staff_id}).first()
        if row is None:
            return None
        out=_row(row)
        out["assignments"] = self.list_assignments(school_id,staff_id,scopes=scopes,include_history=True)
        # These collections are linked to the staff identity, not to a
        # section assignment. A scoped reader must not learn school-wide
        # access memberships, family relationships or global status events.
        if any(kind == "SCHOOL" for kind, _ in scopes):
            out["history"] = self.status_history(school_id,staff_id)
            out["access_links"] = self.access_links(school_id,staff_id)
            out["staff_children"] = self.staff_children(school_id,staff_id)
        else:
            out["history"] = []
            out["access_links"] = []
            out["staff_children"] = []
        return out

    def summary(self, school_id: UUID, *, scopes: tuple[tuple[str, str | None], ...] = ()) -> StaffSummary:
        where_scope, params = _scope_where(scopes)
        stmt = _bind_scope(text(f"""
          WITH visible AS (SELECT sm.* FROM staff_members sm WHERE sm.school_id=:sid AND {where_scope})
          SELECT count(*) total,
                 count(*) FILTER (WHERE status='ACTIVE') active,
                 count(*) FILTER (WHERE status='SUSPENDED') suspended,
                 count(*) FILTER (WHERE status='LEFT') left_count,
                 count(*) FILTER (WHERE category='ENSEIGNANT') teachers,
                 count(*) FILTER (WHERE category='ADMINISTRATIF') administrative,
                 count(*) FILTER (WHERE category='OUVRIER') workers,
                 count(*) FILTER (WHERE category='AUTRE') other,
                 (SELECT count(*) FROM staff_assignments a JOIN visible v ON v.id=a.staff_id WHERE a.end_date IS NULL) active_assignments,
                 (SELECT count(*) FROM staff_access_links l JOIN visible v ON v.id=l.staff_id WHERE l.active) linked_accounts,
                 (SELECT count(*) FROM staff_student_links sl JOIN visible v ON v.id=sl.staff_id WHERE sl.active) staff_children
            FROM visible
        """), params)
        r=self.connection.execute(stmt,{"sid":school_id,**params}).first()._mapping
        return StaffSummary(total=int(r['total']),active=int(r['active']),suspended=int(r['suspended']),left=int(r['left_count']),
                            teachers=int(r['teachers']),administrative=int(r['administrative']),workers=int(r['workers']),other=int(r['other']),
                            active_assignments=int(r['active_assignments']),linked_accounts=int(r['linked_accounts']),staff_children=int(r['staff_children']))

    def create_staff(self, member: StaffMember) -> dict[str, Any]:
        row=self.connection.execute(text("""
          INSERT INTO staff_members(id,school_id,employee_no,last_name,first_name,middle_name,gender,birth_date,phone,email,address,category,qualification,specialty,hire_date,status,photo_url,notes,version)
          VALUES (:id,:school_id,:employee_no,:last_name,:first_name,:middle_name,:gender,:birth_date,:phone,:email,:address,:category,:qualification,:specialty,:hire_date,:status,:photo_url,:notes,:version)
          RETURNING *
        """), {"id":member.id,"school_id":member.school_id,"employee_no":member.employee_no,"last_name":member.last_name,"first_name":member.first_name,
                 "middle_name":member.middle_name,"gender":member.gender,"birth_date":member.birth_date,"phone":member.phone,"email":member.email,
                 "address":member.address,"category":member.category.value,"qualification":member.qualification,"specialty":member.specialty,
                 "hire_date":member.hire_date,"status":member.status.value,"photo_url":member.photo_url,"notes":member.notes,"version":member.version}).first()
        self.connection.execute(text("""INSERT INTO staff_status_history(school_id,staff_id,from_status,to_status,effective_date,reason)
            VALUES (:sid,:staff,NULL,'ACTIVE',coalesce(:hire,CURRENT_DATE),'CREATION_DOSSIER_AGENT')"""),{"sid":member.school_id,"staff":member.id,"hire":member.hire_date})
        return _row(row)

    def update_staff(self, school_id: UUID, staff_id: UUID, *, expected_version: int, fields: dict[str, Any]) -> dict[str, Any]:
        allowed={"employee_no","last_name","first_name","middle_name","gender","birth_date","phone","email","address","category","qualification","specialty","hire_date","photo_url","notes"}
        patch={k:v for k,v in fields.items() if k in allowed}
        if not patch: raise ValueError("Aucun champ agent modifiable")
        sets=", ".join(f"{k}=:{k}" for k in patch)
        row=self.connection.execute(text(f"UPDATE staff_members SET {sets} WHERE school_id=:sid AND id=:id AND version=:expected RETURNING *"),
                                    {**patch,"sid":school_id,"id":staff_id,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Agent modifié par un autre utilisateur ou introuvable")
        return _row(row)

    def list_functions(self, school_id: UUID, *, enabled_only: bool = False) -> list[dict[str, Any]]:
        clause="AND enabled=true" if enabled_only else ""
        return [_row(r) for r in self.connection.execute(text(f"SELECT * FROM staff_functions WHERE school_id=:sid {clause} ORDER BY sort_order,label"),{"sid":school_id}).all()]

    def create_function(self, function: StaffFunction) -> dict[str, Any]:
        row=self.connection.execute(text("""INSERT INTO staff_functions(id,school_id,code,label,category,enabled,sort_order,version)
          VALUES (:id,:sid,:code,:label,:category,:enabled,:sort_order,:version) RETURNING *"""),
          {"id":function.id,"sid":function.school_id,"code":function.code,"label":function.label,"category":function.category,"enabled":function.enabled,"sort_order":function.sort_order,"version":function.version}).first()
        return _row(row)

    def update_function(self, school_id: UUID, function_id: UUID, *, expected_version:int, label:str, category:str, enabled:bool, sort_order:int=100) -> dict[str,Any]:
        row=self.connection.execute(text("""UPDATE staff_functions SET label=:label,category=:category,enabled=:enabled,sort_order=:sort_order
          WHERE school_id=:sid AND id=:id AND version=:expected RETURNING *"""),{"label":label.strip(),"category":category,"enabled":enabled,"sort_order":sort_order,"sid":school_id,"id":function_id,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Fonction modifiée par un autre utilisateur ou introuvable")
        return _row(row)

    def add_assignment(self, assignment: StaffAssignment) -> dict[str, Any]:
        if assignment.is_primary:
            self.connection.execute(text("UPDATE staff_assignments SET is_primary=false WHERE school_id=:sid AND staff_id=:staff AND end_date IS NULL AND is_primary"),{"sid":assignment.school_id,"staff":assignment.staff_id})
        row=self.connection.execute(text("""
          INSERT INTO staff_assignments(id,school_id,staff_id,function_id,scope_type,scope_value,section_id,class_id,is_primary,is_titular,titular_class_id,start_date,end_date,end_reason,version)
          VALUES (:id,:sid,:staff,:function,:scope_type,:scope_value,:section_id,:class_id,:is_primary,:is_titular,:titular_class_id,:start_date,:end_date,:end_reason,:version)
          RETURNING *
        """),{"id":assignment.id,"sid":assignment.school_id,"staff":assignment.staff_id,"function":assignment.function_id,"scope_type":assignment.scope_type.value,
              "scope_value":assignment.scope_value,"section_id":assignment.section_id,"class_id":assignment.class_id,"is_primary":assignment.is_primary,"is_titular":assignment.is_titular,
              "titular_class_id":assignment.titular_class_id,"start_date":assignment.start_date,"end_date":assignment.end_date,"end_reason":assignment.end_reason,"version":assignment.version}).first()
        return _row(row)

    def list_assignments(self, school_id:UUID, staff_id:UUID, *, scopes:tuple[tuple[str,str|None],...]=(("SCHOOL",None),), include_history:bool=False) -> list[dict[str,Any]]:
        full=any(t=='SCHOOL' for t,_ in scopes)
        clauses=["a.school_id=:sid","a.staff_id=:staff"]
        params:dict[str,Any]={"sid":school_id,"staff":staff_id}
        if not include_history: clauses.append("a.end_date IS NULL")
        if not full:
            sections=sorted({str(v).upper() for t,v in scopes if t=='SECTION' and v});classes=sorted({str(v).upper() for t,v in scopes if t=='CLASS' and v})
            bits=[]
            if sections:
                bits += ["(a.scope_type='SECTION' AND upper(a.scope_value) IN :sections)","(a.scope_type='CLASS' AND EXISTS(SELECT 1 FROM school_classes sc JOIN school_sections ss ON ss.id=sc.section_id WHERE sc.id=a.class_id AND upper(ss.code) IN :sections))"]
                params['sections']=sections
            if classes: bits.append("(a.scope_type='CLASS' AND upper(a.scope_value) IN :classes)");params['classes']=classes
            if not sections and not classes: return []
            clauses.append('('+ ' OR '.join(bits)+')')
        stmt=text(f"""SELECT a.*,f.code function_code,f.label function_label,f.category function_category,
            ss.label section_label,sc.label class_label,tc.label titular_class_label
          FROM staff_assignments a JOIN staff_functions f ON f.id=a.function_id
          LEFT JOIN school_sections ss ON ss.id=a.section_id LEFT JOIN school_classes sc ON sc.id=a.class_id LEFT JOIN school_classes tc ON tc.id=a.titular_class_id
          WHERE {' AND '.join(clauses)} ORDER BY a.end_date NULLS FIRST,a.is_primary DESC,a.start_date DESC""")
        if 'sections' in params: stmt=stmt.bindparams(bindparam('sections',expanding=True))
        if 'classes' in params: stmt=stmt.bindparams(bindparam('classes',expanding=True))
        return [_row(r) for r in self.connection.execute(stmt,params).all()]

    def end_assignment(self, school_id:UUID, assignment_id:UUID, *, expected_version:int, effective_date:date, reason:str) -> dict[str,Any]:
        if not reason.strip(): raise ValueError("Motif de fin d'affectation obligatoire")
        row=self.connection.execute(text("""UPDATE staff_assignments SET end_date=:d,end_reason=:reason,is_primary=false
          WHERE school_id=:sid AND id=:id AND version=:expected AND end_date IS NULL AND :d>=start_date RETURNING *"""),
          {"d":effective_date,"reason":reason.strip(),"sid":school_id,"id":assignment_id,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Affectation déjà clôturée, modifiée ou date invalide")
        return _row(row)

    def exit_staff(self, school_id:UUID, staff_id:UUID, *, expected_version:int, effective_date:date, reason:str, actor_user_id:UUID) -> dict[str,Any]:
        reason=reason.strip()
        if not reason: raise ValueError("Motif de sortie obligatoire")
        before=self.connection.execute(text("SELECT * FROM staff_members WHERE school_id=:sid AND id=:id FOR UPDATE"),{"sid":school_id,"id":staff_id}).first()
        if before is None: raise LookupError("Agent introuvable")
        m=before._mapping
        if int(m['version'])!=expected_version: raise OptimisticConcurrencyError("Agent modifié par un autre utilisateur")
        if m['status']=='LEFT': raise ValueError("Cet agent est déjà sorti")
        if m['hire_date'] and effective_date < m['hire_date']: raise ValueError("Date de sortie antérieure à l'engagement")
        self.connection.execute(text("""UPDATE staff_assignments SET end_date=:d,end_reason=:reason,is_primary=false
            WHERE school_id=:sid AND staff_id=:staff AND end_date IS NULL"""),{"d":effective_date,"reason":f"SORTIE_AGENT: {reason}","sid":school_id,"staff":staff_id})
        links=self.connection.execute(text("SELECT membership_id FROM staff_access_links WHERE school_id=:sid AND staff_id=:staff AND active=true FOR UPDATE"),{"sid":school_id,"staff":staff_id}).all()
        membership_ids=[r[0] for r in links]
        if membership_ids:
            stmt=text("UPDATE school_memberships SET active=false,version=version+1 WHERE school_id=:sid AND id IN :ids").bindparams(bindparam('ids',expanding=True))
            self.connection.execute(stmt,{"sid":school_id,"ids":membership_ids})
            self.connection.execute(text("UPDATE staff_access_links SET active=false,unlinked_at=now(),reason=:reason WHERE school_id=:sid AND staff_id=:staff AND active=true"),{"reason":f"SORTIE_AGENT: {reason}","sid":school_id,"staff":staff_id})
        row=self.connection.execute(text("""UPDATE staff_members SET status='LEFT',exit_date=:d,exit_reason=:reason
            WHERE school_id=:sid AND id=:id AND version=:expected RETURNING *"""),{"d":effective_date,"reason":reason,"sid":school_id,"id":staff_id,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Conflit de sortie agent")
        self.connection.execute(text("""INSERT INTO staff_status_history(school_id,staff_id,from_status,to_status,effective_date,reason,actor_user_id)
            VALUES (:sid,:staff,:from_status,'LEFT',:d,:reason,:actor)"""),{"sid":school_id,"staff":staff_id,"from_status":m['status'],"d":effective_date,"reason":reason,"actor":actor_user_id})
        return _row(row)

    def reactivate_staff(self, school_id:UUID, staff_id:UUID, *, expected_version:int, effective_date:date, reason:str, actor_user_id:UUID) -> dict[str,Any]:
        reason=reason.strip()
        if not reason: raise ValueError("Motif de réactivation obligatoire")
        before=self.connection.execute(text("SELECT * FROM staff_members WHERE school_id=:sid AND id=:id FOR UPDATE"),{"sid":school_id,"id":staff_id}).first()
        if before is None: raise LookupError("Agent introuvable")
        m=before._mapping
        if int(m['version'])!=expected_version: raise OptimisticConcurrencyError("Agent modifié par un autre utilisateur")
        if m['status']!='LEFT': raise ValueError("Seul un ancien agent peut être réactivé")
        row=self.connection.execute(text("""UPDATE staff_members SET status='ACTIVE',exit_date=NULL,exit_reason=NULL
          WHERE school_id=:sid AND id=:id AND version=:expected RETURNING *"""),{"sid":school_id,"id":staff_id,"expected":expected_version}).first()
        self.connection.execute(text("""INSERT INTO staff_status_history(school_id,staff_id,from_status,to_status,effective_date,reason,actor_user_id)
          VALUES (:sid,:staff,'LEFT','ACTIVE',:d,:reason,:actor)"""),{"sid":school_id,"staff":staff_id,"d":effective_date,"reason":reason,"actor":actor_user_id})
        # Deliberately do not reopen old assignments or linked membership.
        return _row(row)

    def status_history(self, school_id:UUID, staff_id:UUID) -> list[dict[str,Any]]:
        return [_row(r) for r in self.connection.execute(text("SELECT * FROM staff_status_history WHERE school_id=:sid AND staff_id=:staff ORDER BY effective_date DESC,created_at DESC"),{"sid":school_id,"staff":staff_id}).all()]

    def list_status_history(self, school_id:UUID, *, scopes:tuple[tuple[str,str|None],...], limit:int=100, offset:int=0) -> list[dict[str,Any]]:
        visible=self._visible_staff_ids(school_id,scopes)
        args:dict[str,Any]={"sid":school_id,"limit":max(1,min(limit,500)),"offset":max(0,offset)}
        stmt=text("""SELECT h.*,sm.employee_no,sm.last_name,sm.first_name,sm.middle_name
          FROM staff_status_history h JOIN staff_members sm ON sm.id=h.staff_id
          WHERE h.school_id=:sid
          ORDER BY h.effective_date DESC,h.created_at DESC LIMIT :limit OFFSET :offset""")
        if visible is not None:
            if not visible: return []
            stmt=text("""SELECT h.*,sm.employee_no,sm.last_name,sm.first_name,sm.middle_name
              FROM staff_status_history h JOIN staff_members sm ON sm.id=h.staff_id
              WHERE h.school_id=:sid AND h.staff_id IN :ids
              ORDER BY h.effective_date DESC,h.created_at DESC LIMIT :limit OFFSET :offset""").bindparams(bindparam("ids",expanding=True))
            args["ids"]=list(visible)
        return [_row(r) for r in self.connection.execute(stmt,args).all()]

    def access_links(self, school_id:UUID, staff_id:UUID) -> list[dict[str,Any]]:
        return [_row(r) for r in self.connection.execute(text("""SELECT l.*,m.user_id,m.active membership_active,u.email,u.full_name
          FROM staff_access_links l JOIN school_memberships m ON m.id=l.membership_id JOIN users u ON u.id=m.user_id
          WHERE l.school_id=:sid AND l.staff_id=:staff ORDER BY l.active DESC,l.linked_at DESC"""),{"sid":school_id,"staff":staff_id}).all()]

    def link_access(self, school_id:UUID, staff_id:UUID, membership_id:UUID, *, reason:str|None=None) -> dict[str,Any]:
        row=self.connection.execute(text("""INSERT INTO staff_access_links(school_id,staff_id,membership_id,active,reason)
          VALUES (:sid,:staff,:mid,true,:reason)
          ON CONFLICT(school_id,staff_id,membership_id) DO UPDATE SET active=true,unlinked_at=NULL,reason=EXCLUDED.reason
          RETURNING *"""),{"sid":school_id,"staff":staff_id,"mid":membership_id,"reason":reason}).first()
        return _row(row)

    def unlink_access(self, school_id:UUID, staff_id:UUID, membership_id:UUID, *, reason:str) -> dict[str,Any]:
        if not reason.strip(): raise ValueError("Motif de déliaison obligatoire")
        row=self.connection.execute(text("""UPDATE staff_access_links SET active=false,unlinked_at=now(),reason=:reason
          WHERE school_id=:sid AND staff_id=:staff AND membership_id=:mid AND active=true RETURNING *"""),{"reason":reason.strip(),"sid":school_id,"staff":staff_id,"mid":membership_id}).first()
        if row is None: raise LookupError("Lien d'accès actif introuvable")
        return _row(row)

    def staff_children(self, school_id:UUID, staff_id:UUID) -> list[dict[str,Any]]:
        return [_row(r) for r in self.connection.execute(text("""SELECT l.*,p.responsibility_mode,p.effective_from,p.effective_until,p.version preference_version
          FROM staff_student_links l LEFT JOIN staff_student_finance_preferences p ON p.staff_student_link_id=l.id
          WHERE l.school_id=:sid AND l.staff_id=:staff AND l.active ORDER BY l.created_at DESC"""),{"sid":school_id,"staff":staff_id}).all()]

    def link_student(self, school_id:UUID, staff_id:UUID, student_id:UUID, *, relationship:str='PARENT') -> dict[str,Any]:
        row=self.connection.execute(text("""INSERT INTO staff_student_links(school_id,staff_id,student_id,relationship,active)
          VALUES (:sid,:staff,:student,:rel,true)
          ON CONFLICT(school_id,staff_id,student_id) DO UPDATE SET active=true,ended_at=NULL,relationship=EXCLUDED.relationship
          RETURNING *"""),{"sid":school_id,"staff":staff_id,"student":student_id,"rel":relationship.strip().upper() or 'PARENT'}).first()
        return _row(row)

    def set_student_finance_mode(self, school_id:UUID, link_id:UUID, *, mode:str, effective_from:date, effective_until:date|None, notes:str|None) -> dict[str,Any]:
        row=self.connection.execute(text("""INSERT INTO staff_student_finance_preferences(school_id,staff_student_link_id,responsibility_mode,effective_from,effective_until,notes)
          VALUES (:sid,:link,:mode,:start,:end,:notes)
          ON CONFLICT(school_id,staff_student_link_id) DO UPDATE SET responsibility_mode=EXCLUDED.responsibility_mode,effective_from=EXCLUDED.effective_from,effective_until=EXCLUDED.effective_until,notes=EXCLUDED.notes
          RETURNING *"""),{"sid":school_id,"link":link_id,"mode":mode,"start":effective_from,"end":effective_until,"notes":notes}).first()
        return _row(row)
