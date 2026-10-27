from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from edusync.modules.schooling.domain.models import Family, Guardian, Enrollment, Student, StudentBenefit, normalized_phone
from edusync.shared.domain.concurrency import OptimisticConcurrencyError


def _row(row) -> dict[str, Any]:
    return dict(row._mapping)


def _student_scope_where(scopes: tuple[tuple[str, str | None], ...], *, alias: str = "s") -> tuple[str, dict[str, Any]]:
    if any(t == "SCHOOL" for t, _ in scopes):
        return "TRUE", {}
    sections = sorted({str(v).upper() for t, v in scopes if t == "SECTION" and v})
    classes = sorted({str(v).upper() for t, v in scopes if t == "CLASS" and v})
    if not sections and not classes:
        return "FALSE", {}
    clauses: list[str] = []
    params: dict[str, Any] = {}
    if sections:
        clauses.append("upper(ss.code) IN :scope_sections")
        params["scope_sections"] = sections
    if classes:
        clauses.append("upper(sc.code) IN :scope_classes")
        params["scope_classes"] = classes
    return f"EXISTS (SELECT 1 FROM enrollments e JOIN school_classes sc ON sc.id=e.class_id JOIN school_sections ss ON ss.id=sc.section_id WHERE e.school_id={alias}.school_id AND e.student_id={alias}.id AND e.status<>'CANCELLED' AND ({' OR '.join(clauses)}))", params


def _bind_scope(stmt, params: dict[str, Any]):
    if "scope_sections" in params:
        stmt = stmt.bindparams(bindparam("scope_sections", expanding=True))
    if "scope_classes" in params:
        stmt = stmt.bindparams(bindparam("scope_classes", expanding=True))
    return stmt


def _family_scope_where(scopes: tuple[tuple[str, str | None], ...], *, alias: str = "f") -> tuple[str, dict[str, Any]]:
    if any(t == "SCHOOL" for t, _ in scopes):
        return "TRUE", {}
    student_where, params = _student_scope_where(scopes, alias="sv")
    return f"EXISTS (SELECT 1 FROM students sv WHERE sv.school_id={alias}.school_id AND sv.family_id={alias}.id AND {student_where})", params


@dataclass(slots=True)
class PostgresSchoolingRepository:
    connection: Connection

    def next_code(self, school_id: UUID, namespace: str, prefix: str) -> str:
        n = self.connection.execute(text("""
          INSERT INTO school_sequence_counters(school_id,namespace,current_value) VALUES (:sid,:ns,1)
          ON CONFLICT(school_id,namespace) DO UPDATE SET current_value=school_sequence_counters.current_value+1,updated_at=now()
          RETURNING current_value
        """), {"sid": school_id, "ns": namespace}).scalar_one()
        return f"{prefix}-{int(n):05d}"

    def active_year(self, school_id: UUID) -> dict[str, Any] | None:
        r = self.connection.execute(text("SELECT * FROM academic_years WHERE school_id=:sid AND status='ACTIVE'"), {"sid": school_id}).first()
        return _row(r) if r else None

    def enrollment_policy(self, school_id: UUID) -> dict[str, Any]:
        row=self.connection.execute(text("SELECT payload FROM school_policy_documents WHERE school_id=:sid AND kind='ENROLLMENT' AND status='ACTIVE'"),{"sid":school_id}).first()
        default={"required_student_fields":["last_name","middle_name","first_name","class_id"],"guardian_required_at_enrollment":False,"guardian_phone_required":False}
        if not row:return default
        payload=row._mapping.get('payload') or {}
        return {**default,**dict(payload)}

    def class_info(self, school_id: UUID, class_id: UUID) -> dict[str, Any] | None:
        r=self.connection.execute(text("""SELECT sc.*,ss.code section_code,ss.label section_label,ay.code academic_year_code,ay.status academic_year_status
          FROM school_classes sc JOIN school_sections ss ON ss.id=sc.section_id JOIN academic_years ay ON ay.id=sc.academic_year_id
          WHERE sc.school_id=:sid AND sc.id=:id"""),{"sid":school_id,"id":class_id}).first()
        return _row(r) if r else None

    def create_family(self, family: Family) -> dict[str, Any]:
        r=self.connection.execute(text("""INSERT INTO families(id,school_id,code,display_name,display_name_origin,phone,email,address,contact_status,notes,version)
          VALUES (:id,:sid,:code,:name,:origin,:phone,:email,:address,:contact,:notes,:version) RETURNING *"""),
          {"id":family.id,"sid":family.school_id,"code":family.code,"name":family.display_name,"origin":family.display_name_origin.value,"phone":family.phone,"email":family.email,"address":family.address,"contact":family.contact_status.value,"notes":family.notes,"version":family.version}).first()
        return _row(r)

    def update_family(self, school_id:UUID, family_id:UUID, *, expected_version:int, patch:dict[str,Any]) -> dict[str,Any]:
        allowed={"display_name","display_name_origin","phone","email","address","contact_status","notes"}; patch={k:v for k,v in patch.items() if k in allowed}
        if not patch: raise ValueError("Aucune donnée de foyer à modifier")
        sets=[];args={"sid":school_id,"id":family_id,"expected":expected_version}
        for i,(k,v) in enumerate(patch.items()): sets.append(f"{k}=:p{i}");args[f"p{i}"]=v
        r=self.connection.execute(text(f"UPDATE families SET {','.join(sets)} WHERE school_id=:sid AND id=:id AND version=:expected RETURNING *"),args).first()
        if not r: raise OptimisticConcurrencyError("Foyer modifié par un autre utilisateur")
        return _row(r)

    def create_guardian(self, guardian: Guardian) -> dict[str, Any]:
        r=self.connection.execute(text("""INSERT INTO guardians(id,school_id,full_name,phone,normalized_phone,email,address,occupation,notes,version)
          VALUES (:id,:sid,:name,:phone,:norm,:email,:address,:occupation,:notes,:version) RETURNING *"""),
          {"id":guardian.id,"sid":guardian.school_id,"name":guardian.full_name,"phone":guardian.phone,"norm":normalized_phone(guardian.phone),"email":guardian.email,"address":guardian.address,"occupation":guardian.occupation,"notes":guardian.notes,"version":guardian.version}).first()
        return _row(r)

    def link_guardian(self, school_id:UUID, *, family_id:UUID, guardian_id:UUID, role:str, is_primary:bool) -> dict[str,Any]:
        if is_primary:
            self.connection.execute(text("UPDATE family_guardians SET is_primary=false WHERE school_id=:sid AND family_id=:fid AND active"),{"sid":school_id,"fid":family_id})
        r=self.connection.execute(text("""INSERT INTO family_guardians(school_id,family_id,guardian_id,role,is_primary,active)
          VALUES (:sid,:fid,:gid,:role,:primary,true)
          ON CONFLICT(school_id,family_id,guardian_id) DO UPDATE SET role=EXCLUDED.role,is_primary=EXCLUDED.is_primary,active=true
          RETURNING *"""),{"sid":school_id,"fid":family_id,"gid":guardian_id,"role":role,"primary":is_primary}).first()
        return _row(r)

    def get_family(self, school_id:UUID, family_id:UUID, *, scopes:tuple[tuple[str,str|None],...] = (("SCHOOL",None),)) -> dict[str,Any]|None:
        scope_where,params=_family_scope_where(scopes)
        stmt=_bind_scope(text(f"SELECT * FROM families f WHERE f.school_id=:sid AND f.id=:id AND {scope_where}"),params)
        r=self.connection.execute(stmt,{"sid":school_id,"id":family_id,**params}).first()
        if not r:return None
        out=_row(r)
        out["guardians"]=[_row(x) for x in self.connection.execute(text("""SELECT fg.*,g.full_name,g.phone,g.email,g.address,g.occupation
          FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.school_id=:sid AND fg.family_id=:fid AND fg.active ORDER BY fg.is_primary DESC,fg.created_at"""),{"sid":school_id,"fid":family_id}).all()]
        student_where,student_params=_student_scope_where(scopes,alias="s")
        child_stmt=_bind_scope(text(f"""SELECT s.*,e.id enrollment_id,e.academic_year_id,e.class_id,e.status enrollment_status,sc.label class_label,ss.code section_code
          FROM students s LEFT JOIN enrollments e ON e.student_id=s.id AND e.school_id=s.school_id AND e.status<>'CANCELLED'
          LEFT JOIN school_classes sc ON sc.id=e.class_id LEFT JOIN school_sections ss ON ss.id=sc.section_id
          WHERE s.school_id=:sid AND s.family_id=:fid AND {student_where} ORDER BY s.last_name,s.middle_name,s.first_name,e.enrolled_on DESC"""),student_params)
        out["children"]=[_row(x) for x in self.connection.execute(child_stmt,{"sid":school_id,"fid":family_id,**student_params}).all()]
        return out

    def resolve_households(self, school_id:UUID, query:str, *, scopes:tuple[tuple[str,str|None],...] = (("SCHOOL",None),), limit:int=20) -> list[dict[str,Any]]:
        q=query.strip()
        if not q:return []
        norm=normalized_phone(q)
        family_scope,scope_params=_family_scope_where(scopes)
        child_scope,child_params=_student_scope_where(scopes,alias='s')
        merged_params={**scope_params,**child_params}
        stmt=text(f"""WITH matches AS (
          SELECT f.id family_id,
            max(CASE WHEN lower(f.code)=lower(:q) THEN 100 WHEN lower(f.display_name)=lower(:q) THEN 80 WHEN f.phone=:norm THEN 90 ELSE 45 END) score,
            array_remove(array_agg(DISTINCT src),NULL) sources
          FROM (
            SELECT f.*, 'FAMILY'::text src FROM families f WHERE f.school_id=:sid AND (f.code ILIKE :like OR f.display_name ILIKE :like OR coalesce(f.phone,'')=:norm)
            UNION ALL
            SELECT f.*, 'GUARDIAN'::text src FROM families f JOIN family_guardians fg ON fg.family_id=f.id AND fg.active JOIN guardians g ON g.id=fg.guardian_id
              WHERE f.school_id=:sid AND (g.full_name ILIKE :like OR coalesce(g.normalized_phone,'')=:norm)
            UNION ALL
            SELECT f.*, 'STUDENT'::text src FROM families f JOIN students s ON s.family_id=f.id
              WHERE f.school_id=:sid AND (s.matricule ILIKE :like OR concat_ws(' ',s.last_name,s.middle_name,s.first_name) ILIKE :like)
          ) f GROUP BY f.id
        ) SELECT f.*,m.score,m.sources,
          (SELECT count(*) FROM students s WHERE s.school_id=f.school_id AND s.family_id=f.id AND {child_scope}) child_count,
          (SELECT jsonb_agg(jsonb_build_object('id',g.id,'full_name',g.full_name,'phone',g.phone,'role',fg.role,'is_primary',fg.is_primary) ORDER BY fg.is_primary DESC) FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.school_id=f.school_id AND fg.family_id=f.id AND fg.active) guardians
          FROM matches m JOIN families f ON f.id=m.family_id WHERE {family_scope} ORDER BY m.score DESC,f.display_name LIMIT :lim""")
        stmt=_bind_scope(stmt,merged_params)
        rows=self.connection.execute(stmt,{"sid":school_id,"q":q,"like":f"%{q}%","norm":norm or "__none__","lim":max(1,min(limit,50)),**merged_params}).all()
        items=[_row(r) for r in rows]
        # Exact phone/code only becomes CERTAIN when unique; names and shared phones remain POSSIBLE.
        for item in items:
            item["confidence"]="CERTAIN" if len(items)==1 and int(item.get("score") or 0)>=90 else "POSSIBLE"
        return items

    def record_household_resolution(self, school_id:UUID, *, query_text:str|None, selected_family_id:UUID|None, confidence:str, candidate_count:int, resolution:str, actor_user_id:UUID)->None:
        self.connection.execute(text("""INSERT INTO household_resolution_events(school_id,query_text,selected_family_id,confidence,candidate_count,resolution,actor_user_id)
          VALUES (:sid,:q,:fid,:confidence,:count,:resolution,:actor)"""),{"sid":school_id,"q":query_text,"fid":selected_family_id,"confidence":confidence,"count":candidate_count,"resolution":resolution,"actor":actor_user_id})

    def create_student(self, student: Student) -> dict[str, Any]:
        r=self.connection.execute(text("""INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name,gender,birth_date,birth_place,nationality,address,previous_school,photo_url,status,profile_completeness,notes,version)
          VALUES (:id,:sid,:fid,:mat,:last,:middle,:first,:gender,:birth,:birth_place,:nationality,:address,:previous,:photo,:status,:complete,:notes,:version) RETURNING *"""),
          {"id":student.id,"sid":student.school_id,"fid":student.family_id,"mat":student.matricule,"last":student.last_name,"middle":student.middle_name,"first":student.first_name,"gender":student.gender,"birth":student.birth_date,"birth_place":student.birth_place,"nationality":student.nationality,"address":student.address,"previous":student.previous_school,"photo":student.photo_url,"status":student.status.value,"complete":student.profile_completeness,"notes":student.notes,"version":student.version}).first()
        return _row(r)

    def create_enrollment(self, enrollment: Enrollment) -> dict[str, Any]:
        r=self.connection.execute(text("""INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id,status,enrollment_kind,enrolled_on,origin_school,notes,version)
          VALUES (:id,:sid,:student,:year,:class,:status,:kind,:day,:origin,:notes,:version) RETURNING *"""),
          {"id":enrollment.id,"sid":enrollment.school_id,"student":enrollment.student_id,"year":enrollment.academic_year_id,"class":enrollment.class_id,"status":enrollment.status.value,"kind":enrollment.enrollment_kind,"day":enrollment.enrolled_on,"origin":enrollment.origin_school,"notes":enrollment.notes,"version":enrollment.version}).first()
        self.connection.execute(text("INSERT INTO class_assignments(school_id,student_id,enrollment_id,class_id,effective_from,reason) VALUES (:sid,:student,:enrollment,:class,:day,'INSCRIPTION')"),{"sid":enrollment.school_id,"student":enrollment.student_id,"enrollment":enrollment.id,"class":enrollment.class_id,"day":enrollment.enrolled_on})
        return _row(r)

    def add_benefit(self, benefit:StudentBenefit)->dict[str,Any]:
        r=self.connection.execute(text("""INSERT INTO student_benefits(id,school_id,student_id,academic_year_id,kind,source_reference,selected_explicitly,active,notes,version,configured_percent,applies_to_fee_code,applies_to_fee_codes)
          VALUES (:id,:sid,:student,:year,:kind,:source,true,:active,:notes,:version,:pct,:fee,:fees)
          ON CONFLICT(school_id,student_id,academic_year_id,kind) DO UPDATE SET source_reference=EXCLUDED.source_reference,active=EXCLUDED.active,notes=EXCLUDED.notes,
            configured_percent=EXCLUDED.configured_percent,applies_to_fee_code=EXCLUDED.applies_to_fee_code,applies_to_fee_codes=EXCLUDED.applies_to_fee_codes
          RETURNING *"""),{"pct":benefit.configured_percent,"fee":benefit.applies_to_fee_code,"fees":list(benefit.applies_to_fee_codes) or None,"id":benefit.id,"sid":benefit.school_id,"student":benefit.student_id,"year":benefit.academic_year_id,"kind":benefit.kind.value,"source":benefit.source_reference,"active":benefit.active,"notes":benefit.notes,"version":benefit.version}).first()
        return _row(r)

    def _visible_ids(self, school_id:UUID, scopes:tuple[tuple[str,str|None],...])->set[UUID]|None:
        if any(t=='SCHOOL' for t,_ in scopes):return None
        where,params=_student_scope_where(scopes)
        stmt=_bind_scope(text(f"SELECT s.id FROM students s WHERE s.school_id=:sid AND {where}"),params)
        return {r[0] for r in self.connection.execute(stmt,{"sid":school_id,**params}).all()}

    def list_students(self, school_id:UUID, *, scopes:tuple[tuple[str,str|None],...], q:str|None=None, class_id:UUID|None=None, status:str|None=None, academic_year_id:UUID|None=None, section_id:UUID|None=None, gender:str|None=None, all_years:bool=False, limit:int=200, offset:int=0, option_id:UUID|None=None)->list[dict[str,Any]]:
        where,params=_student_scope_where(scopes);conditions=["s.school_id=:sid",where];args={"sid":school_id,**params}
        # The selected enrollment itself must be authorized. Otherwise a
        # pupil visible through one section can reveal a newer enrollment
        # in a different section via the lateral join and exports.
        lateral_scope = "TRUE" if any(t=="SCHOOL" for t,_ in scopes) else (
            "(upper(ss1.code) IN :lateral_sections OR upper(sc1.code) IN :lateral_classes)"
            if any(t in ("SECTION","CLASS") and v for t,v in scopes) else "FALSE")
        args["lateral_sections"] = sorted({str(v).upper() for t,v in scopes if t=="SECTION" and v})
        args["lateral_classes"] = sorted({str(v).upper() for t,v in scopes if t=="CLASS" and v})
        if all_years:
            enrollment_join=f"""LEFT JOIN LATERAL (SELECT e1.* FROM enrollments e1 JOIN school_classes sc1 ON sc1.id=e1.class_id JOIN school_sections ss1 ON ss1.id=sc1.section_id JOIN academic_years ay1 ON ay1.id=e1.academic_year_id WHERE e1.school_id=s.school_id AND e1.student_id=s.id AND e1.status<>'CANCELLED' AND {lateral_scope} ORDER BY ay1.start_date DESC,e1.enrolled_on DESC LIMIT 1) e ON true"""
        else:
            if academic_year_id:
                args['year_id']=academic_year_id
                enrollment_join=f"""LEFT JOIN LATERAL (SELECT e1.* FROM enrollments e1 JOIN school_classes sc1 ON sc1.id=e1.class_id JOIN school_sections ss1 ON ss1.id=sc1.section_id WHERE e1.school_id=s.school_id AND e1.student_id=s.id AND e1.status<>'CANCELLED' AND {lateral_scope} AND e1.academic_year_id=:year_id ORDER BY e1.enrolled_on DESC LIMIT 1) e ON true"""
            else:
                enrollment_join=f"""LEFT JOIN LATERAL (SELECT e1.* FROM enrollments e1 JOIN school_classes sc1 ON sc1.id=e1.class_id JOIN school_sections ss1 ON ss1.id=sc1.section_id JOIN academic_years ay1 ON ay1.id=e1.academic_year_id WHERE e1.school_id=s.school_id AND e1.student_id=s.id AND e1.status<>'CANCELLED' AND {lateral_scope} AND ay1.status='ACTIVE' ORDER BY e1.enrolled_on DESC LIMIT 1) e ON true"""
        # A scoped directory must never return a pupil without an enrollment
        # in the requested year (or any authorized year for all_years).
        # A school-wide reader retains the legacy all_years behavior.
        if not all_years or not any(t=="SCHOOL" for t,_ in scopes):
            conditions.append("e.id IS NOT NULL")
        if q and q.strip():conditions.append("(s.matricule ILIKE :q OR concat_ws(' ',s.last_name,s.middle_name,s.first_name) ILIKE :q OR f.display_name ILIKE :q OR coalesce(f.phone,'') ILIKE :q OR EXISTS(SELECT 1 FROM family_guardians fgq JOIN guardians gq ON gq.id=fgq.guardian_id WHERE fgq.family_id=s.family_id AND fgq.active AND (gq.full_name ILIKE :q OR coalesce(gq.phone,'') ILIKE :q)))");args['q']=f"%{q.strip()}%"
        if class_id:conditions.append("e.class_id=:class_id");args['class_id']=class_id
        if section_id:conditions.append("sc.section_id=:section_id");args['section_id']=section_id
        # Directory filtered by Humanités option (students module pass 2026-10-25, Desktop parity of the class filters).
        if option_id:conditions.append("sc.option_id=:option_id");args['option_id']=option_id
        if status:conditions.append("s.status=:status");args['status']=status
        if gender in {'M','F'}:conditions.append("s.gender=:gender");args['gender']=gender
        stmt=text(f"""SELECT s.*,f.code family_code,f.display_name family_name,f.phone family_phone,f.contact_status,
          e.id enrollment_id,e.academic_year_id,e.class_id,e.status enrollment_status,e.enrollment_kind,e.enrolled_on,
          ay.code academic_year_code,ay.label academic_year_label,
          sc.label class_label,sc.code class_code,sc.option_id class_option_id,sc.reference_code class_reference_code,ss.id section_id,ss.code section_code,ss.label section_label,
          (SELECT g.full_name FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.school_id=s.school_id AND fg.family_id=s.family_id AND fg.active ORDER BY fg.is_primary DESC,fg.created_at LIMIT 1) primary_responsible,
          (SELECT g.phone FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.school_id=s.school_id AND fg.family_id=s.family_id AND fg.active ORDER BY fg.is_primary DESC,fg.created_at LIMIT 1) primary_responsible_phone,
          EXISTS(SELECT 1 FROM staff_student_links sl WHERE sl.school_id=s.school_id AND sl.student_id=s.id AND sl.active) staff_child,
          EXISTS(SELECT 1 FROM student_benefits b WHERE b.school_id=s.school_id AND b.student_id=s.id AND b.kind='LARGE_FAMILY' AND b.active) large_family_beneficiary
          FROM students s JOIN families f ON f.id=s.family_id
          {enrollment_join}
          LEFT JOIN academic_years ay ON ay.id=e.academic_year_id
          LEFT JOIN school_classes sc ON sc.id=e.class_id LEFT JOIN school_sections ss ON ss.id=sc.section_id
          WHERE {' AND '.join(conditions)} ORDER BY s.last_name,s.middle_name,s.first_name LIMIT :limit OFFSET :offset""")
        if lateral_scope not in ("TRUE","FALSE"):
            stmt=stmt.bindparams(bindparam("lateral_sections",expanding=True),
                                 bindparam("lateral_classes",expanding=True))
        stmt=_bind_scope(stmt,params);args['limit']=max(1,min(limit,1000));args['offset']=max(0,offset)
        return [_row(r) for r in self.connection.execute(stmt,args).all()]

    def get_student(self, school_id:UUID, student_id:UUID, *, scopes:tuple[tuple[str,str|None],...])->dict[str,Any]|None:
        visible=self._visible_ids(school_id,scopes)
        if visible is not None and student_id not in visible:return None
        r=self.connection.execute(text("""SELECT s.*,f.code family_code,f.display_name family_name,f.phone family_phone,f.contact_status
          FROM students s JOIN families f ON f.id=s.family_id WHERE s.school_id=:sid AND s.id=:id"""),{"sid":school_id,"id":student_id}).first()
        if not r:return None
        out=_row(r)
        # An otherwise visible student may have enrollment history in a different
        # section. Filter each enrollment row; student visibility alone is insufficient.
        enrollment_scopes = sorted({str(v).upper() for t,v in scopes if t=="SECTION" and v})
        class_scopes = sorted({str(v).upper() for t,v in scopes if t=="CLASS" and v})
        schoolwide = any(t=="SCHOOL" for t,_ in scopes)
        history_where = "TRUE" if schoolwide else (
            "(upper(ss.code) IN :history_sections OR upper(sc.code) IN :history_classes)"
            if enrollment_scopes or class_scopes else "FALSE"
        )
        history_params = {"sid":school_id,"id":student_id}
        if not schoolwide and (enrollment_scopes or class_scopes):
            history_params.update(history_sections=enrollment_scopes,history_classes=class_scopes)
        history_stmt = text(f"""SELECT e.*,ay.code academic_year_code,ay.label academic_year_label,
              sc.code class_code,sc.label class_label,ss.code section_code,ss.label section_label
              FROM enrollments e JOIN academic_years ay ON ay.id=e.academic_year_id
              JOIN school_classes sc ON sc.id=e.class_id
              JOIN school_sections ss ON ss.id=sc.section_id
              WHERE e.school_id=:sid AND e.student_id=:id AND {history_where}
              ORDER BY ay.start_date DESC""")
        if not schoolwide and (enrollment_scopes or class_scopes):
            history_stmt = history_stmt.bindparams(
                bindparam("history_sections", expanding=True),
                bindparam("history_classes", expanding=True))
        out['enrollments']=[_row(x) for x in self.connection.execute(history_stmt,history_params).all()]
        out['guardians']=[_row(x) for x in self.connection.execute(text("""SELECT g.*,fg.role,fg.is_primary FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.school_id=:sid AND fg.family_id=:fid AND fg.active ORDER BY fg.is_primary DESC"""),{"sid":school_id,"fid":out['family_id']}).all()]
        out['benefits']=[_row(x) for x in self.connection.execute(text("SELECT * FROM student_benefits WHERE school_id=:sid AND student_id=:id ORDER BY created_at DESC"),{"sid":school_id,"id":student_id}).all()]
        out['history']=[_row(x) for x in self.connection.execute(text("SELECT * FROM student_status_events WHERE school_id=:sid AND student_id=:id ORDER BY effective_date DESC,created_at DESC"),{"sid":school_id,"id":student_id}).all()]
        return out

    def update_student(self, school_id:UUID, student_id:UUID, *, expected_version:int, patch:dict[str,Any])->dict[str,Any]:
        allowed={"last_name","middle_name","first_name","gender","birth_date","birth_place","nationality","address","previous_school","photo_url","notes"};patch={k:v for k,v in patch.items() if k in allowed}
        for key in ('last_name','middle_name','first_name'):
            if key in patch and not str(patch[key] or '').strip():raise ValueError("Nom, postnom et prénom ne peuvent pas être vides")
        if not patch:raise ValueError("Aucune donnée élève à modifier")
        current=self.connection.execute(text("SELECT * FROM students WHERE school_id=:sid AND id=:id FOR UPDATE"),{"sid":school_id,"id":student_id}).first()
        if not current:raise LookupError("Élève introuvable")
        row=_row(current)
        if int(row['version'])!=expected_version:raise OptimisticConcurrencyError("Fiche élève modifiée par un autre utilisateur")
        merged={**row,**patch}
        fields=[merged.get('last_name'),merged.get('middle_name'),merged.get('first_name'),merged.get('family_id'),merged.get('gender'),merged.get('birth_date'),merged.get('birth_place'),merged.get('nationality'),merged.get('address'),merged.get('previous_school')]
        completeness=round(sum(1 for x in fields if x not in (None,''))*100/len(fields))
        sets=[];args={"sid":school_id,"id":student_id,"expected":expected_version,"complete":completeness}
        for i,(k,v) in enumerate(patch.items()):sets.append(f"{k}=:p{i}");args[f'p{i}']=v
        sets.append("profile_completeness=:complete")
        r=self.connection.execute(text(f"UPDATE students SET {','.join(sets)} WHERE school_id=:sid AND id=:id AND version=:expected RETURNING *"),args).first()
        if not r:raise OptimisticConcurrencyError("Fiche élève modifiée par un autre utilisateur")
        return _row(r)

    def change_status(self, school_id:UUID, student_id:UUID, *, expected_version:int, event_type:str, effective_date:date, reason:str, actor_user_id:UUID, destination:str|None=None)->dict[str,Any]:
        before=self.connection.execute(text("SELECT * FROM students WHERE school_id=:sid AND id=:id FOR UPDATE"),{"sid":school_id,"id":student_id}).first()
        if not before:raise LookupError("Élève introuvable")
        if int(before._mapping['version'])!=expected_version:raise OptimisticConcurrencyError("Fiche élève modifiée par un autre utilisateur")
        reason=reason.strip()
        if not reason:raise ValueError("Motif obligatoire")
        target={"ABANDON":"ABANDON","TRANSFER":"TRANSFERRED","SUSPEND":"SUSPENDED","REINTEGRATE":"ACTIVE"}.get(event_type)
        if target is None:raise ValueError("Transition invalide")
        # N3-H — Desktop change_student_status invariants.
        previous=before._mapping['status']
        if previous==target:raise ValueError("L’élève possède déjà ce statut")
        if event_type=='REINTEGRATE' and previous not in {'ABANDON','TRANSFERRED','SUSPENDED'}:
            raise ValueError("Une réintégration suppose un statut antérieur abandon, transfert ou suspension")
        if event_type=='TRANSFER' and not (destination or '').strip():raise ValueError("Destination du transfert obligatoire")
        event_id=self.connection.execute(text("INSERT INTO student_status_events(school_id,student_id,event_type,effective_date,reason,destination,actor_user_id) VALUES (:sid,:student,:event,:d,:reason,:destination,:actor) RETURNING id"),{"sid":school_id,"student":student_id,"event":event_type,"d":effective_date,"reason":reason,"destination":destination,"actor":actor_user_id}).scalar_one()
        self._apply_lifecycle_to_future_charges(school_id,student_id,event_id=event_id,event_type=event_type,effective_date=effective_date,reason=reason)
        if event_type in {'ABANDON','TRANSFER'}:
            self.connection.execute(text("UPDATE class_assignments SET effective_until=:d,reason=:reason WHERE school_id=:sid AND student_id=:student AND effective_until IS NULL"),{"d":effective_date,"reason":event_type+': '+reason,"sid":school_id,"student":student_id})
        elif event_type=='REINTEGRATE':
            active_enrollment=self.connection.execute(text("""SELECT e.id,e.class_id FROM enrollments e JOIN academic_years ay ON ay.id=e.academic_year_id WHERE e.school_id=:sid AND e.student_id=:student AND ay.status='ACTIVE' AND e.status<>'CANCELLED' ORDER BY e.enrolled_on DESC LIMIT 1"""),{"sid":school_id,"student":student_id}).first()
            if not active_enrollment: raise ValueError("Réintégration impossible sans inscription dans l’année active")
            self.connection.execute(text("UPDATE class_assignments SET effective_until=:d,reason='REINTEGRATION_REPLACEMENT' WHERE school_id=:sid AND enrollment_id=:eid AND effective_until IS NULL"),{"d":effective_date,"sid":school_id,"eid":active_enrollment._mapping['id']})
            self.connection.execute(text("INSERT INTO class_assignments(school_id,student_id,enrollment_id,class_id,effective_from,reason) VALUES (:sid,:student,:eid,:class,:d,'REINTEGRATE')"),{"sid":school_id,"student":student_id,"eid":active_enrollment._mapping['id'],"class":active_enrollment._mapping['class_id'],"d":effective_date})
        r=self.connection.execute(text("UPDATE students SET status=:status WHERE school_id=:sid AND id=:id AND version=:expected RETURNING *"),{"status":target,"sid":school_id,"id":student_id,"expected":expected_version}).first()
        return _row(r)

    def _apply_lifecycle_to_future_charges(self, school_id:UUID, student_id:UUID, *, event_id, event_type:str, effective_date:date, reason:str)->None:
        """Desktop apply_lifecycle_to_future_charges: neutralize only unpaid future obligations; history and settlements stay."""
        enrollment=self.connection.execute(text("""SELECT e.id FROM enrollments e JOIN academic_years ay ON ay.id=e.academic_year_id
          WHERE e.school_id=:sid AND e.student_id=:st AND ay.status='ACTIVE' AND e.status='VALIDATED'"""),{"sid":school_id,"st":student_id}).scalar_one_or_none()
        if enrollment is None:return
        if event_type=='REINTEGRATE':
            restored=[r[0] for r in self.connection.execute(text("""DELETE FROM finance_charge_lifecycle_states l USING finance_charges c
              WHERE l.charge_id=c.id AND c.school_id=:sid AND c.enrollment_id=:e RETURNING l.charge_id"""),{"sid":school_id,"e":enrollment}).all()]
            if restored:
                self.connection.execute(text("UPDATE finance_charges SET status='ACTIVE' WHERE school_id=:sid AND id=ANY(:ids)"),{"sid":school_id,"ids":restored})
            return
        if event_type not in {'ABANDON','TRANSFER','SUSPEND'}:return
        rows=self.connection.execute(text("""SELECT c.id FROM finance_charges c WHERE c.school_id=:sid AND c.enrollment_id=:e AND c.status='ACTIVE'
          AND c.due_date IS NOT NULL AND c.due_date>=:d AND c.paid_amount=0
          AND NOT EXISTS (SELECT 1 FROM finance_charge_regularizations r WHERE r.school_id=c.school_id AND r.charge_id=c.id)"""),
          {"sid":school_id,"e":enrollment,"d":effective_date}).all()
        for (cid,) in rows:
            self.connection.execute(text("""INSERT INTO finance_charge_lifecycle_states(charge_id,school_id,event_id,effective_on,reason)
              VALUES (:c,:sid,:ev,:d,:r) ON CONFLICT (charge_id) DO UPDATE SET event_id=EXCLUDED.event_id,effective_on=EXCLUDED.effective_on,reason=EXCLUDED.reason"""),
              {"c":cid,"sid":school_id,"ev":event_id,"d":effective_date,"r":f"{event_type}: {reason}"})
            self.connection.execute(text("UPDATE finance_charges SET status='CANCELLED' WHERE id=:c AND school_id=:sid"),{"c":cid,"sid":school_id})

    def summary(self, school_id:UUID, *, scopes:tuple[tuple[str,str|None],...])->dict[str,int]:
        where,params=_student_scope_where(scopes)
        stmt=_bind_scope(text(f"""WITH visible AS (SELECT s.* FROM students s WHERE s.school_id=:sid AND {where})
          SELECT count(*) total_students,count(*) FILTER(WHERE status='ACTIVE') active_students,
            count(*) FILTER(WHERE status='ABANDON') abandoned,count(*) FILTER(WHERE status='TRANSFERRED') transferred,
            (SELECT count(DISTINCT e.student_id) FROM enrollments e JOIN visible v ON v.id=e.student_id WHERE e.enrollment_kind='NEW' AND e.status<>'CANCELLED') new_enrollments,
            (SELECT count(DISTINCT e.student_id) FROM enrollments e JOIN visible v ON v.id=e.student_id WHERE e.enrollment_kind='REENROLLMENT' AND e.status<>'CANCELLED') reenrollments,
            (SELECT count(DISTINCT v.family_id) FROM visible v) families,
            (SELECT count(DISTINCT f.id) FROM families f JOIN visible v ON v.family_id=f.id WHERE f.contact_status='TO_COMPLETE') families_to_complete,
            (SELECT count(DISTINCT fg.guardian_id) FROM family_guardians fg JOIN visible v ON v.family_id=fg.family_id WHERE fg.active) guardians,
            (SELECT count(*) FROM (SELECT family_id FROM visible GROUP BY family_id HAVING count(*)>=5) x) large_family_candidates,
            (SELECT count(DISTINCT sl.student_id) FROM staff_student_links sl JOIN visible v ON v.id=sl.student_id WHERE sl.active) staff_children
          FROM visible"""),params)
        r=self.connection.execute(stmt,{"sid":school_id,**params}).first()._mapping
        return {k:int(r[k] or 0) for k in r.keys()}

    def get_student_unscoped(self, school_id:UUID, student_id:UUID)->dict[str,Any]|None:
        r=self.connection.execute(text("SELECT * FROM students WHERE school_id=:sid AND id=:id"),{"sid":school_id,"id":student_id}).first()
        return _row(r) if r else None

    def benefit_policy(self, school_id:UUID, academic_year_id:UUID, benefit_type:str)->dict[str,Any]|None:
        """Desktop _policy_for: the ENABLED policy of the year for this benefit type, else None."""
        r=self.connection.execute(text("""SELECT * FROM school_benefit_policies WHERE school_id=:sid AND academic_year_id=:y
          AND benefit_type=:t AND enabled"""),{"sid":school_id,"y":academic_year_id,"t":benefit_type}).first()
        return _row(r) if r else None

    def count_benefits(self, school_id:UUID, academic_year_id:UUID, kind:str, *, family_id:UUID|None=None, staff_id:UUID|None=None)->int:
        if family_id is not None:
            sql="""SELECT count(*) FROM student_benefits b JOIN students s ON s.id=b.student_id AND s.school_id=b.school_id
              WHERE b.school_id=:sid AND b.academic_year_id=:y AND b.kind=:k AND b.active AND s.family_id=:ref"""; ref=family_id
        else:
            sql="""SELECT count(*) FROM student_benefits WHERE school_id=:sid AND academic_year_id=:y AND kind=:k AND active
              AND source_reference=:ref"""; ref=str(staff_id)
        return int(self.connection.execute(text(sql),{"sid":school_id,"y":academic_year_id,"k":kind,"ref":ref}).scalar_one() or 0)

    def count_family_enrolled_children(self, school_id:UUID, family_id:UUID, academic_year_id:UUID)->int:
        return int(self.connection.execute(text("""SELECT count(DISTINCT s.id) FROM students s JOIN enrollments e ON e.student_id=s.id AND e.school_id=s.school_id
          WHERE s.school_id=:sid AND s.family_id=:fid AND e.academic_year_id=:year AND e.status='VALIDATED'"""),{"sid":school_id,"fid":family_id,"year":academic_year_id}).scalar_one() or 0)

    def link_staff_child(self, school_id:UUID, *, staff_id:UUID, student_id:UUID)->dict[str,Any]:
        r=self.connection.execute(text("""INSERT INTO staff_student_links(school_id,staff_id,student_id,relationship,active)
          VALUES (:sid,:staff,:student,'CHILD',true)
          ON CONFLICT(school_id,staff_id,student_id) DO UPDATE SET active=true,relationship='CHILD',ended_at=NULL RETURNING *"""),{"sid":school_id,"staff":staff_id,"student":student_id}).first()
        return _row(r)

    def end_guardian_link(self, school_id:UUID, *, family_id:UUID, guardian_id:UUID)->dict[str,Any]:
        r=self.connection.execute(text("UPDATE family_guardians SET active=false,is_primary=false WHERE school_id=:sid AND family_id=:fid AND guardian_id=:gid AND active RETURNING *"),{"sid":school_id,"fid":family_id,"gid":guardian_id}).first()
        if not r:raise LookupError("Responsable actif introuvable")
        return _row(r)

    def change_class(self, school_id:UUID, student_id:UUID, *, target_class_id:UUID, effective_date:date, reason:str, actor_user_id:UUID)->dict[str,Any]:
        target=self.class_info(school_id,target_class_id)
        if not target or not bool(target.get('enabled',True)) or str(target.get('academic_year_status'))!='ACTIVE':raise ValueError("Classe cible inactive ou hors année active")
        enrollment=self.connection.execute(text("""SELECT e.* FROM enrollments e JOIN academic_years ay ON ay.id=e.academic_year_id WHERE e.school_id=:sid AND e.student_id=:student AND ay.status='ACTIVE' AND e.status<>'CANCELLED' ORDER BY e.enrolled_on DESC LIMIT 1 FOR UPDATE OF e"""),{"sid":school_id,"student":student_id}).first()
        if not enrollment:raise ValueError("Aucune inscription active pour ce changement de classe")
        e=_row(enrollment)
        if UUID(str(e['class_id']))==target_class_id:return e
        # Desktop parity (app/db/operations.py, change of class): fail closed once due charges exist — the financial
        # transfer policy has to be decided explicitly before this case (OWNER_DECISION_REQUIRED).
        charged=self.connection.execute(text("SELECT count(*) FROM finance_charges WHERE school_id=:sid AND enrollment_id=:eid AND status='ACTIVE'"),
                                        {"sid":school_id,"eid":e['id']}).scalar_one()
        if charged:raise ValueError("Changement de classe bloqué : des frais dus existent déjà pour cette inscription. La politique de transfert financier doit être décidée explicitement avant ce cas.")
        reason=reason.strip()
        if not reason:raise ValueError("Motif obligatoire")
        self.connection.execute(text("UPDATE class_assignments SET effective_until=:d,reason=:reason WHERE school_id=:sid AND enrollment_id=:eid AND effective_until IS NULL"),{"d":effective_date,"reason":"CLASS_CHANGE: "+reason,"sid":school_id,"eid":e['id']})
        self.connection.execute(text("INSERT INTO class_assignments(school_id,student_id,enrollment_id,class_id,effective_from,reason) VALUES (:sid,:student,:eid,:class,:d,:reason)"),{"sid":school_id,"student":student_id,"eid":e['id'],"class":target_class_id,"d":effective_date,"reason":"CLASS_CHANGE: "+reason})
        self.connection.execute(text("INSERT INTO student_status_events(school_id,student_id,event_type,effective_date,reason,destination,actor_user_id) VALUES (:sid,:student,'CLASS_CHANGE',:d,:reason,:destination,:actor)"),{"sid":school_id,"student":student_id,"d":effective_date,"reason":reason,"destination":str(target.get('label') or target.get('code')),"actor":actor_user_id})
        r=self.connection.execute(text("UPDATE enrollments SET class_id=:class WHERE school_id=:sid AND id=:eid RETURNING *"),{"class":target_class_id,"sid":school_id,"eid":e['id']}).first()
        return _row(r)

    def list_families(self, school_id:UUID, *, scopes:tuple[tuple[str,str|None],...], q:str|None=None, contact_status:str|None=None, large_family_only:bool=False, academic_year_id:UUID|None=None, enrolled_only:bool=False, limit:int=200, offset:int=0)->list[dict[str,Any]]:
        visible=self._visible_ids(school_id,scopes)
        child_scope,child_params=_student_scope_where(scopes,alias='s')
        args:dict[str,Any]={"sid":school_id,"limit":max(1,min(limit,1000)),"offset":max(0,offset),**child_params}
        conditions=["f.school_id=:sid"]
        if visible is not None:
            if not visible:return []
            conditions.append("EXISTS(SELECT 1 FROM students sv WHERE sv.family_id=f.id AND sv.id IN :visible_ids)")
            args['visible_ids']=list(visible)
        if q and q.strip():
            conditions.append("(f.code ILIKE :q OR f.display_name ILIKE :q OR coalesce(f.phone,'') ILIKE :q OR EXISTS(SELECT 1 FROM family_guardians fgq JOIN guardians gq ON gq.id=fgq.guardian_id WHERE fgq.family_id=f.id AND fgq.active AND (gq.full_name ILIKE :q OR coalesce(gq.phone,'') ILIKE :q)))")
            args['q']=f"%{q.strip()}%"
        if contact_status:conditions.append("f.contact_status=:contact_status");args['contact_status']=contact_status
        if large_family_only:conditions.append(f"(SELECT count(*) FROM students s WHERE s.family_id=f.id AND s.school_id=f.school_id AND {child_scope})>=5")
        year_filter=""
        if academic_year_id:
            args['year_id']=academic_year_id
            year_filter=" AND e.academic_year_id=:year_id"
        elif enrolled_only:
            year_filter=" AND EXISTS(SELECT 1 FROM academic_years ayx WHERE ayx.id=e.academic_year_id AND ayx.status='ACTIVE')"
        # The enrollment being counted must belong to the caller's scope,
        # not merely some other enrollment of the same pupil.
        enrollment_clauses = []
        if "scope_sections" in child_params:
            enrollment_clauses.append("upper(ss.code) IN :scope_sections")
        if "scope_classes" in child_params:
            enrollment_clauses.append("upper(sc.code) IN :scope_classes")
        enrollment_scope = ("TRUE" if any(t=="SCHOOL" for t,_ in scopes) else
                            "(" + " OR ".join(enrollment_clauses) + ")"
                            if enrollment_clauses else "FALSE")
        enrollment_joins = " JOIN school_classes sc ON sc.id=e.class_id JOIN school_sections ss ON ss.id=sc.section_id"
        if enrolled_only:
            conditions.append(f"EXISTS(SELECT 1 FROM students se JOIN enrollments e ON e.student_id=se.id AND e.school_id=se.school_id{enrollment_joins} WHERE se.school_id=f.school_id AND se.family_id=f.id AND e.status<>'CANCELLED' AND {enrollment_scope}{year_filter})")
        enrolled_count_sql=f"""(SELECT count(DISTINCT s.id) FROM students s JOIN enrollments e ON e.student_id=s.id AND e.school_id=s.school_id{enrollment_joins} WHERE s.school_id=f.school_id AND s.family_id=f.id AND {enrollment_scope} AND e.status<>'CANCELLED'{year_filter})""" if (academic_year_id or enrolled_only) else f"(SELECT count(*) FROM students s WHERE s.school_id=f.school_id AND s.family_id=f.id AND {child_scope})"
        stmt=text(f"""SELECT f.*,
          (SELECT count(*) FROM students s WHERE s.school_id=f.school_id AND s.family_id=f.id AND {child_scope}) child_count,
          {enrolled_count_sql} enrolled_children,
          (SELECT g.full_name FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.school_id=f.school_id AND fg.family_id=f.id AND fg.active ORDER BY fg.is_primary DESC,fg.created_at LIMIT 1) primary_responsible,
          (SELECT g.phone FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.school_id=f.school_id AND fg.family_id=f.id AND fg.active ORDER BY fg.is_primary DESC,fg.created_at LIMIT 1) primary_responsible_phone,
          (SELECT jsonb_agg(jsonb_build_object('id',g.id,'full_name',g.full_name,'phone',g.phone,'role',fg.role,'is_primary',fg.is_primary) ORDER BY fg.is_primary DESC) FROM family_guardians fg JOIN guardians g ON g.id=fg.guardian_id WHERE fg.school_id=f.school_id AND fg.family_id=f.id AND fg.active) guardians
          FROM families f WHERE {' AND '.join(conditions)} ORDER BY f.display_name LIMIT :limit OFFSET :offset""")
        stmt=_bind_scope(stmt,child_params)
        if visible is not None: stmt=stmt.bindparams(bindparam('visible_ids',expanding=True))
        return [_row(r) for r in self.connection.execute(stmt,args).all()]
