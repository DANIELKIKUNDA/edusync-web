from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import bindparam, text
from sqlalchemy.engine import Connection

from edusync.modules.effectifs.domain.models import HeadcountRow, row_from_mapping


def _rows(result): return [dict(r._mapping) for r in result]


def _scope_sql(scopes:tuple[tuple[str,str|None],...], requested_scope:str, *, section_alias:str="ss", class_alias:str="sc") -> tuple[str,dict[str,Any]]:
    """Intersect UI scope with capability scope; never widen actor visibility."""
    requested=(requested_scope or "ALL").upper()
    school=any(t=="SCHOOL" for t,_ in scopes)
    allowed_sections={str(v).upper() for t,v in scopes if t in {"SECTION","CYCLE"} and v}
    allowed_classes={str(v).upper() for t,v in scopes if t=="CLASS" and v}
    clauses=[];params:dict[str,Any]={}
    if not school:
        permitted=[]
        if allowed_sections:
            permitted.append(f"upper({section_alias}.code) IN :allowed_sections");params["allowed_sections"]=sorted(allowed_sections)
        if allowed_classes:
            permitted.append(f"upper({class_alias}.code) IN :allowed_classes");params["allowed_classes"]=sorted(allowed_classes)
        if not permitted:return "FALSE",{}
        clauses.append("("+" OR ".join(permitted)+")")
    if requested!="ALL":
        clauses.append(f"upper({section_alias}.code)=:requested_section");params["requested_section"]=requested
    return (" AND ".join(clauses) if clauses else "TRUE"),params


def _bind(stmt,params):
    if "allowed_sections" in params:stmt=stmt.bindparams(bindparam("allowed_sections",expanding=True))
    if "allowed_classes" in params:stmt=stmt.bindparams(bindparam("allowed_classes",expanding=True))
    return stmt


@dataclass(slots=True)
class PostgresEffectifsRepository:
    connection:Connection

    def school_identity(self,school_id:UUID)->dict[str,Any]:
        r=self.connection.execute(text("SELECT id,name,code,logo_url,email,phone,address,city,province FROM schools WHERE id=:sid"),{"sid":school_id}).first()
        return dict(r._mapping) if r else {"name":"EduSync École"}

    def year(self,school_id:UUID,year_id:UUID|None=None)->dict[str,Any]|None:
        if year_id:
            r=self.connection.execute(text("SELECT * FROM academic_years WHERE school_id=:sid AND id=:id"),{"sid":school_id,"id":year_id}).first()
        else:r=self.connection.execute(text("SELECT * FROM academic_years WHERE school_id=:sid AND status='ACTIVE'"),{"sid":school_id}).first()
        return dict(r._mapping) if r else None

    def classes(self,school_id:UUID,year_id:UUID,*,scopes,scope:str)->list[dict[str,Any]]:
        where,params=_scope_sql(scopes,scope)
        stmt=_bind(text(f"""SELECT sc.id,sc.code,sc.label,ss.id section_id,ss.code section_code,ss.label section_label
          FROM school_classes sc JOIN school_sections ss ON ss.id=sc.section_id
          WHERE sc.school_id=:sid AND sc.academic_year_id=:yid AND sc.enabled AND {where} ORDER BY ss.code,sc.label"""),params)
        return _rows(self.connection.execute(stmt,{"sid":school_id,"yid":year_id,**params}).all())

    def _base_flags_cte(self,where:str)->str:
        return f"""
        WITH base AS (
          SELECT e.id enrollment_id,e.student_id,e.class_id,s.gender,sc.code class_code,sc.label class_label,
                 ss.code section_code,ss.label section_label,coalesce(so.code,'') option_code,coalesce(so.label,'Sans option') option_label,
                 ay.start_date,ay.end_date,
                 EXISTS(SELECT 1 FROM student_status_events ev WHERE ev.school_id=e.school_id AND ev.student_id=e.student_id AND ev.event_type='ABANDON' AND ev.effective_date BETWEEN ay.start_date AND ay.end_date
                   AND NOT EXISTS(SELECT 1 FROM student_status_events ri WHERE ri.school_id=ev.school_id AND ri.student_id=ev.student_id AND ri.event_type='REINTEGRATE' AND ri.effective_date>=ev.effective_date AND ri.effective_date<=ay.end_date)) AS abandoned,
                 EXISTS(SELECT 1 FROM student_status_events ev WHERE ev.school_id=e.school_id AND ev.student_id=e.student_id AND ev.event_type='TRANSFER' AND ev.effective_date BETWEEN ay.start_date AND ay.end_date) AS transferred
          FROM enrollments e JOIN students s ON s.id=e.student_id AND s.school_id=e.school_id
          JOIN school_classes sc ON sc.id=e.class_id AND sc.school_id=e.school_id
          JOIN school_sections ss ON ss.id=sc.section_id AND ss.school_id=e.school_id
          LEFT JOIN school_options so ON so.id=sc.option_id AND so.school_id=e.school_id
          JOIN academic_years ay ON ay.id=e.academic_year_id AND ay.school_id=e.school_id
          WHERE e.school_id=:sid AND e.academic_year_id=:yid AND e.status<>'CANCELLED' AND {where}
        )
        """

    def counts(self,school_id:UUID,year_id:UUID,*,scopes,scope:str,group_by:str)->list[HeadcountRow]:
        if group_by not in {"class","section","option"}:raise ValueError("Regroupement d'effectifs invalide")
        where,params=_scope_sql(scopes,scope)
        if group_by=="class": section="section_label";label="class_label";code="class_code";group="section_label,class_label,class_code"
        elif group_by=="section": section="section_label";label="section_label";code="section_code";group="section_label,section_code"
        else: section="section_label";label="option_label";code="option_code";group="section_label,option_label,option_code"
        sql=self._base_flags_cte(where)+f"""
        SELECT {section} section_label,{label} label,{code} code,
          count(*) FILTER (WHERE gender='F')::int enrolled_f,count(*) FILTER (WHERE gender='M')::int enrolled_m,count(*)::int enrolled_t,
          count(*) FILTER (WHERE abandoned AND gender='F')::int abandoned_f,count(*) FILTER (WHERE abandoned AND gender='M')::int abandoned_m,count(*) FILTER (WHERE abandoned)::int abandoned_t,
          count(*) FILTER (WHERE transferred AND gender='F')::int transferred_f,count(*) FILTER (WHERE transferred AND gender='M')::int transferred_m,count(*) FILTER (WHERE transferred)::int transferred_t,
          count(*) FILTER (WHERE NOT abandoned AND NOT transferred AND gender='F')::int active_f,
          count(*) FILTER (WHERE NOT abandoned AND NOT transferred AND gender='M')::int active_m,
          count(*) FILTER (WHERE NOT abandoned AND NOT transferred)::int active_t
        FROM base GROUP BY {group} ORDER BY section_label,label
        """
        stmt=_bind(text(sql),params)
        return [row_from_mapping(r._mapping) for r in self.connection.execute(stmt,{"sid":school_id,"yid":year_id,**params}).all()]

    def overview(self,school_id:UUID,year_id:UUID,*,scopes,scope:str)->dict[str,Any]:
        rows=self.counts(school_id,year_id,scopes=scopes,scope=scope,group_by="class")
        active=sum(r.active.total for r in rows);girls=sum(r.active.female for r in rows);boys=sum(r.active.male for r in rows);classes=len(rows)
        return {"active_students":active,"active_girls":girls,"active_boys":boys,"active_classes":classes,"average_per_class":round(active/classes,2) if classes else 0}

    def movements(self,school_id:UUID,year_id:UUID,*,scopes,scope:str,class_id:UUID|None=None,event_type:str|None=None,q:str|None=None,limit:int=50,offset:int=0)->dict[str,Any]:
        where,params=_scope_sql(scopes,scope)
        clauses=[where,"ev.effective_date BETWEEN ay.start_date AND ay.end_date"]
        args={"sid":school_id,"yid":year_id,"limit":limit,"offset":offset,**params}
        if class_id:clauses.append("sc.id=:cid");args["cid"]=class_id
        if event_type:clauses.append("ev.event_type=:etype");args["etype"]=event_type
        if q:
            clauses.append("(s.matricule ILIKE :q OR concat_ws(' ',s.last_name,s.middle_name,s.first_name) ILIKE :q OR ev.reason ILIKE :q)");args["q"]="%"+q.strip()+"%"
        w=" AND ".join(clauses)
        base=f"""FROM student_status_events ev JOIN students s ON s.id=ev.student_id AND s.school_id=ev.school_id
          JOIN enrollments e ON e.school_id=ev.school_id AND e.student_id=ev.student_id AND e.academic_year_id=:yid AND e.status<>'CANCELLED'
          JOIN school_classes sc ON sc.id=e.class_id JOIN school_sections ss ON ss.id=sc.section_id JOIN academic_years ay ON ay.id=e.academic_year_id
          WHERE ev.school_id=:sid AND {w}"""
        count_stmt=_bind(text("SELECT count(*) "+base),params);total=int(self.connection.execute(count_stmt,args).scalar_one())
        stmt=_bind(text(f"""SELECT ev.id,ev.event_type,ev.effective_date,ev.reason,ev.destination,s.matricule,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student_name,s.gender,ss.label section_label,sc.label class_label
          {base} ORDER BY ev.effective_date DESC,ev.created_at DESC LIMIT :limit OFFSET :offset"""),params)
        return {"items":_rows(self.connection.execute(stmt,args).all()),"total":total,"limit":limit,"offset":offset}

    def contribution_types(self,school_id:UUID)->list[dict[str,Any]]:
        return _rows(self.connection.execute(text("SELECT id,code,label,unit FROM contribution_types WHERE school_id=:sid AND enabled ORDER BY label"),{"sid":school_id}).all())

    def deposits(self,school_id:UUID,year_id:UUID,*,scopes,scope:str,class_id:UUID|None=None,contribution_type_id:UUID|None=None,q:str|None=None,limit:int=100,offset:int=0)->dict[str,Any]:
        where,params=_scope_sql(scopes,scope)
        clauses=[where];args={"sid":school_id,"yid":year_id,"limit":limit,"offset":offset,**params}
        if class_id:clauses.append("sc.id=:cid");args["cid"]=class_id
        if contribution_type_id:clauses.append("mc.contribution_type_id=:ctid");args["ctid"]=contribution_type_id
        if q:clauses.append("(s.matricule ILIKE :q OR concat_ws(' ',s.last_name,s.middle_name,s.first_name) ILIKE :q OR ct.label ILIKE :q)");args["q"]="%"+q.strip()+"%"
        w=" AND ".join(clauses)
        base=f"""FROM material_contributions mc JOIN students s ON s.id=mc.student_id AND s.school_id=mc.school_id
          JOIN enrollments e ON e.id=mc.enrollment_id AND e.school_id=mc.school_id JOIN school_classes sc ON sc.id=e.class_id JOIN school_sections ss ON ss.id=sc.section_id
          JOIN contribution_types ct ON ct.id=mc.contribution_type_id LEFT JOIN users u ON u.id=mc.recorded_by
          WHERE mc.school_id=:sid AND mc.academic_year_id=:yid AND {w}"""
        total=int(self.connection.execute(_bind(text("SELECT count(*) "+base),params),args).scalar_one())
        stmt=_bind(text(f"""SELECT mc.id,mc.deposited_on,mc.quantity,mc.notes,s.matricule,concat_ws(' ',s.last_name,s.middle_name,s.first_name) student_name,s.gender,
          ss.label section_label,sc.label class_label,ct.label contribution_label,ct.unit,coalesce(u.full_name,'—') recorded_by_name
          {base} ORDER BY mc.deposited_on DESC,mc.created_at DESC LIMIT :limit OFFSET :offset"""),params)
        return {"items":_rows(self.connection.execute(stmt,args).all()),"total":total,"limit":limit,"offset":offset}

    def enrollment_in_scope(self,school_id:UUID,enrollment_id:UUID,*,scopes,scope:str)->dict[str,Any]|None:
        where,params=_scope_sql(scopes,scope)
        stmt=_bind(text(f"""SELECT e.id,e.student_id,e.academic_year_id,e.class_id,ay.status academic_year_status,ss.code section_code,sc.code class_code
          FROM enrollments e JOIN academic_years ay ON ay.id=e.academic_year_id JOIN school_classes sc ON sc.id=e.class_id JOIN school_sections ss ON ss.id=sc.section_id
          WHERE e.school_id=:sid AND e.id=:eid AND e.status<>'CANCELLED' AND {where}"""),params)
        r=self.connection.execute(stmt,{"sid":school_id,"eid":enrollment_id,**params}).first()
        return dict(r._mapping) if r else None

    def record_deposit(self,school_id:UUID,*,student_id:UUID,enrollment_id:UUID,academic_year_id:UUID,contribution_type_id:UUID,quantity:Decimal,deposited_on,notes:str|None,recorded_by:UUID,client_operation_id:UUID|None)->dict[str,Any]:
        r=self.connection.execute(text("""INSERT INTO material_contributions(school_id,academic_year_id,student_id,enrollment_id,contribution_type_id,quantity,deposited_on,notes,recorded_by,client_operation_id)
          VALUES (:sid,:yid,:student,:enrollment,:type,:qty,:day,:notes,:actor,:op) RETURNING *"""),{"sid":school_id,"yid":academic_year_id,"student":student_id,"enrollment":enrollment_id,"type":contribution_type_id,"qty":quantity,"day":deposited_on,"notes":notes,"actor":recorded_by,"op":client_operation_id}).first()
        return dict(r._mapping)
