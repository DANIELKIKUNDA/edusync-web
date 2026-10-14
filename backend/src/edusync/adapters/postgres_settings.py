from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.modules.settings.domain.models import AcademicYear, AcademicYearStatus, compute_readiness
from edusync.shared.domain.concurrency import OptimisticConcurrencyError


def _m(row):
    return row._mapping


@dataclass(slots=True)
class PostgresSettingsRepository:
    connection: Connection

    # ---------- reference catalogs ----------
    def reference_catalog(self) -> dict[str, list[dict[str, Any]]]:
        sections=[dict(_m(r)) for r in self.connection.execute(text(
            "SELECT code,label,sort_order FROM rdc_reference_sections ORDER BY sort_order"
        )).all()]
        classes=[dict(_m(r)) for r in self.connection.execute(text(
            "SELECT code,section_code,label,sort_order FROM rdc_reference_classes ORDER BY sort_order"
        )).all()]
        fees=[dict(_m(r)) for r in self.connection.execute(text(
            "SELECT code,label,periodicity,default_currency,sort_order FROM rdc_reference_fee_types ORDER BY sort_order"
        )).all()]
        return {"sections":sections,"classes":classes,"fee_types":fees}

    # ---------- readiness ----------
    def readiness(self, school_id: UUID):
        school=self.connection.execute(text("SELECT name FROM schools WHERE id=:sid"),{"sid":school_id}).first()
        if school is None: raise LookupError("École introuvable")
        def count(sql:str)->int:
            return int(self.connection.execute(text(sql),{"sid":school_id}).scalar_one())
        bootstrap=self.connection.execute(text(
            "SELECT internal_notifications_enabled,external_sms_enabled,suggested_year_code,version FROM settings_bootstrap_state WHERE school_id=:sid"
        ),{"sid":school_id}).first()
        internal=True if bootstrap is None else bool(_m(bootstrap)["internal_notifications_enabled"])
        sms=False if bootstrap is None else bool(_m(bootstrap)["external_sms_enabled"])
        snap=compute_readiness(
            school_id=school_id,has_identity=bool(_m(school)["name"].strip()),
            active_years=count("SELECT count(*) FROM academic_years WHERE school_id=:sid AND status='ACTIVE'"),
            enabled_sections=count("SELECT count(*) FROM school_sections WHERE school_id=:sid AND enabled"),
            enabled_classes=count("SELECT count(*) FROM school_classes WHERE school_id=:sid AND enabled"),
            active_fee_types=count("SELECT count(*) FROM fee_types WHERE school_id=:sid AND enabled"),
            active_tariffs=count("SELECT count(*) FROM tariffs WHERE school_id=:sid AND enabled"),
            internal_notifications_enabled=internal,external_sms_enabled=sms,
        )
        return snap, None if bootstrap is None else dict(_m(bootstrap))

    # ---------- academic year ----------
    @staticmethod
    def _year(row) -> AcademicYear:
        m=_m(row)
        return AcademicYear(id=m['id'],school_id=m['school_id'],code=m['code'],label=m['label'],
                            start_date=m['start_date'],end_date=m['end_date'],status=AcademicYearStatus(m['status']),
                            created_at=m['created_at'],updated_at=m['updated_at'],version=int(m['version']))

    def list_academic_years(self, school_id: UUID) -> list[AcademicYear]:
        rows=self.connection.execute(text("""
            SELECT id,school_id,code,label,start_date,end_date,status,created_at,updated_at,version
              FROM academic_years WHERE school_id=:sid ORDER BY start_date DESC,code DESC
        """),{"sid":school_id}).all()
        return [self._year(r) for r in rows]

    def get_academic_year(self, school_id: UUID, year_id: UUID) -> AcademicYear | None:
        row=self.connection.execute(text("""
            SELECT id,school_id,code,label,start_date,end_date,status,created_at,updated_at,version
              FROM academic_years WHERE school_id=:sid AND id=:id
        """),{"sid":school_id,"id":year_id}).first()
        return None if row is None else self._year(row)

    def add_academic_year(self, year: AcademicYear) -> None:
        self.connection.execute(text("""
            INSERT INTO academic_years(id,school_id,code,label,start_date,end_date,status,created_at,updated_at,version)
            VALUES (:id,:sid,:code,:label,:start,:end,:status,:created,:updated,:version)
        """),{"id":year.id,"sid":year.school_id,"code":year.code,"label":year.label,"start":year.start_date,
                 "end":year.end_date,"status":year.status.value,"created":year.created_at,"updated":year.updated_at,"version":year.version})

    def save_academic_year(self, year: AcademicYear, *, expected_version: int) -> None:
        row=self.connection.execute(text("""
            UPDATE academic_years SET code=:code,label=:label,start_date=:start,end_date=:end,status=:status
             WHERE school_id=:sid AND id=:id AND version=:expected RETURNING version
        """),{"sid":year.school_id,"id":year.id,"code":year.code,"label":year.label,"start":year.start_date,
                 "end":year.end_date,"status":year.status.value,"expected":expected_version}).first()
        if row is None:
            raise OptimisticConcurrencyError("Année scolaire modifiée par une autre session; rechargez les données")
        year.version=int(row[0])

    def activate_academic_year(self, school_id: UUID, year_id: UUID, *, expected_version: int) -> AcademicYear:
        current=self.get_academic_year(school_id,year_id)
        if current is None: raise LookupError("Année scolaire introuvable")
        if current.version != expected_version: raise OptimisticConcurrencyError("Version d'année obsolète")
        # one ACTIVE year, no implicit overwrite: explicit close first.
        other=self.connection.execute(text("SELECT id FROM academic_years WHERE school_id=:sid AND status='ACTIVE' AND id<>:id"),
                                      {"sid":school_id,"id":year_id}).first()
        if other is not None: raise ValueError("Une autre année scolaire est déjà active; clôturez-la d'abord")
        current.activate(); self.save_academic_year(current,expected_version=expected_version); return current

    def transition_academic_year(self, school_id: UUID, year_id: UUID, *, expected_version: int, action: str) -> AcademicYear:
        current=self.get_academic_year(school_id,year_id)
        if current is None: raise LookupError("Année scolaire introuvable")
        if current.version != expected_version: raise OptimisticConcurrencyError("Version d'année obsolète")
        action=action.strip().upper()
        transitions={"CLOSE": current.close, "ARCHIVE": current.archive, "REOPEN": current.reopen}
        fn=transitions.get(action)
        if fn is None: raise ValueError("Transition d'année inconnue")
        fn(); self.save_academic_year(current,expected_version=expected_version); return current

    # ---------- school structure ----------
    def list_sections(self, school_id: UUID) -> list[dict[str, Any]]:
        return [dict(_m(r)) for r in self.connection.execute(text("""
            SELECT id,code,label,enabled,version FROM school_sections WHERE school_id=:sid ORDER BY label
        """),{"sid":school_id}).all()]

    def upsert_section(self, school_id: UUID, *, code:str,label:str,enabled:bool,expected_version:int|None=None) -> dict[str,Any]:
        code=code.strip().upper(); label=label.strip()
        if not code or not label: raise ValueError("Code et libellé de section obligatoires")
        row=self.connection.execute(text("SELECT id,version FROM school_sections WHERE school_id=:sid AND code=:code"),
                                    {"sid":school_id,"code":code}).first()
        if row is None:
            r=self.connection.execute(text("""
                INSERT INTO school_sections(id,school_id,code,label,enabled) VALUES (:id,:sid,:code,:label,:enabled)
                RETURNING id,code,label,enabled,version
            """),{"id":uuid4(),"sid":school_id,"code":code,"label":label,"enabled":enabled}).first()
            return dict(_m(r))
        if expected_version is None or int(_m(row)['version']) != expected_version:
            raise OptimisticConcurrencyError("Version de section obsolète")
        r=self.connection.execute(text("""
            UPDATE school_sections SET label=:label,enabled=:enabled
             WHERE school_id=:sid AND code=:code AND version=:expected
             RETURNING id,code,label,enabled,version
        """),{"sid":school_id,"code":code,"label":label,"enabled":enabled,"expected":expected_version}).first()
        if r is None: raise OptimisticConcurrencyError("Section modifiée par une autre session")
        return dict(_m(r))

    def list_options(self, school_id: UUID) -> list[dict[str,Any]]:
        return [dict(_m(r)) for r in self.connection.execute(text("""
            SELECT o.id,o.section_id,o.code,o.label,o.tariff_group_code,o.enabled,o.version,s.code AS section_code
              FROM school_options o JOIN school_sections s ON s.id=o.section_id
             WHERE o.school_id=:sid ORDER BY s.label,o.label
        """),{"sid":school_id}).all()]

    def upsert_option(self, school_id: UUID, *, section_id:UUID, code:str,label:str,tariff_group_code:str|None=None,
                      enabled:bool=True, expected_version:int|None=None) -> dict[str,Any]:
        code=code.strip().upper();label=label.strip()
        if not code or not label: raise ValueError("Code et libellé d'option obligatoires")
        section=self.connection.execute(text("SELECT id FROM school_sections WHERE id=:id AND school_id=:sid"),{"id":section_id,"sid":school_id}).first()
        if section is None: raise ValueError("Section incompatible avec cette école")
        row=self.connection.execute(text("SELECT id,version FROM school_options WHERE school_id=:sid AND code=:code"),{"sid":school_id,"code":code}).first()
        if row is None:
            r=self.connection.execute(text("""
                INSERT INTO school_options(id,school_id,section_id,code,label,tariff_group_code,enabled)
                VALUES(:id,:sid,:section,:code,:label,:group_code,:enabled)
                RETURNING id,section_id,code,label,tariff_group_code,enabled,version
            """),{"id":uuid4(),"sid":school_id,"section":section_id,"code":code,"label":label,"group_code":tariff_group_code,"enabled":enabled}).first()
            return dict(_m(r))
        if expected_version is None or int(_m(row)['version']) != expected_version:
            raise OptimisticConcurrencyError("Version d'option obsolète")
        r=self.connection.execute(text("""
            UPDATE school_options SET section_id=:section,label=:label,tariff_group_code=:group_code,enabled=:enabled
             WHERE school_id=:sid AND code=:code AND version=:expected
             RETURNING id,section_id,code,label,tariff_group_code,enabled,version
        """),{"sid":school_id,"section":section_id,"code":code,"label":label,"group_code":tariff_group_code,"enabled":enabled,"expected":expected_version}).first()
        if r is None: raise OptimisticConcurrencyError("Option modifiée par une autre session")
        return dict(_m(r))

    def list_classes(self, school_id: UUID, year_id: UUID|None=None) -> list[dict[str,Any]]:
        rows=self.connection.execute(text("""
            SELECT c.id,c.academic_year_id,c.section_id,c.option_id,c.reference_code,c.code,c.label,c.enabled,c.status,c.archived_at,c.version,
                   s.code AS section_code,s.label AS section_label,y.code AS academic_year_code,y.status AS academic_year_status,
                   (SELECT count(*) FROM enrollments e WHERE e.school_id=c.school_id AND e.class_id=c.id AND e.status='VALIDATED') AS student_count
              FROM school_classes c JOIN school_sections s ON s.id=c.section_id JOIN academic_years y ON y.id=c.academic_year_id
             WHERE c.school_id=:sid AND (CAST(:year AS uuid) IS NULL OR c.academic_year_id=:year)
             ORDER BY s.label,c.label
        """),{"sid":school_id,"year":year_id}).all()
        return [dict(_m(r)) for r in rows]

    def create_class(self, school_id: UUID, *, academic_year_id:UUID,section_id:UUID,code:str,label:str,
                     reference_code:str|None=None,option_id:UUID|None=None) -> dict[str,Any]:
        # tenant-consistency checks are explicit; RLS is defence in depth.
        ok=self.connection.execute(text("""
            SELECT y.status,y.label FROM academic_years y JOIN school_sections s ON s.school_id=y.school_id
             WHERE y.id=:y AND s.id=:s AND y.school_id=:sid
        """),{"y":academic_year_id,"s":section_id,"sid":school_id}).first()
        if ok is None: raise ValueError("Année/section incompatible avec cette école")
        if _m(ok)['status'] in ('CLOSED','ARCHIVED'): raise ValueError(f"L'année {_m(ok)['label']} est en lecture seule : aucune classe ne peut y être ouverte")
        if option_id is not None:
            option_ok=self.connection.execute(text("""
                SELECT 1 FROM school_options WHERE id=:option AND school_id=:sid AND section_id=:section AND enabled
            """),{"option":option_id,"sid":school_id,"section":section_id}).first()
            if option_ok is None: raise ValueError("Option incompatible avec la section ou cette école")
        r=self.connection.execute(text("""
            INSERT INTO school_classes(id,school_id,academic_year_id,section_id,option_id,reference_code,code,label)
            VALUES (:id,:sid,:y,:section,:option,:ref,:code,:label)
            RETURNING id,academic_year_id,section_id,option_id,reference_code,code,label,enabled,status,archived_at,version
        """),{"id":uuid4(),"sid":school_id,"y":academic_year_id,"section":section_id,"option":option_id,
                 "ref":reference_code,"code":code.strip().upper(),"label":label.strip()}).first()
        return dict(_m(r))

    # ---------- fee types / tariffs ----------
    def list_fee_types(self, school_id: UUID) -> list[dict[str,Any]]:
        return [dict(_m(r)) for r in self.connection.execute(text("""
            SELECT id,code,label,periodicity,default_currency,regulatory,enabled,version
              FROM fee_types WHERE school_id=:sid ORDER BY label
        """),{"sid":school_id}).all()]

    def create_fee_type(self, school_id: UUID, *, code:str,label:str,periodicity:str,default_currency:str,regulatory:bool=False) -> dict[str,Any]:
        periodicity=periodicity.upper(); currency=default_currency.upper()
        if periodicity not in {'ONE_TIME','MONTHLY','PERIODIC','OPTIONAL'}: raise ValueError("Périodicité invalide")
        if currency not in {'CDF','USD'}: raise ValueError("Devise invalide")
        r=self.connection.execute(text("""
            INSERT INTO fee_types(id,school_id,code,label,periodicity,default_currency,regulatory)
            VALUES (:id,:sid,:code,:label,:periodicity,:currency,:regulatory)
            RETURNING id,code,label,periodicity,default_currency,regulatory,enabled,version
        """),{"id":uuid4(),"sid":school_id,"code":code.strip().upper(),"label":label.strip(),
                 "periodicity":periodicity,"currency":currency,"regulatory":regulatory}).first()
        return dict(_m(r))

    # ---------- tariff rules (Desktop parity, lot L1) ----------
    TARIFF_GROUPS = {"GENERAL": "Humanités générales", "TECHNICAL": "Humanités techniques", "OTHER": "Autre groupe"}
    # Desktop resolve_tariff_for_class priorities.
    TARIFF_PRIORITY = {"CLASS": 600, "ACADEMIC_CLASS": 500, "OPTION_GROUP": 350, "SECTION": 200, "SCHOOL": 100}
    TARIFF_COLUMNS = ("id,academic_year_id,fee_type_id,class_id,section_id,option_id,scope_type,scope_ref,effective_from,status,"
                      "source_reference,currency,amount,billing_months,enabled,version")

    @staticmethod
    def _tariff_out(row) -> dict[str,Any]:
        x = dict(_m(row)); x['amount'] = None if x.get('amount') is None else str(x['amount']); return x

    def list_tariffs(self, school_id: UUID, year_id: UUID|None=None) -> list[dict[str,Any]]:
        rows=self.connection.execute(text("""
            SELECT t.id,t.academic_year_id,t.fee_type_id,t.class_id,t.section_id,t.option_id,t.scope_type,t.scope_ref,
                   t.effective_from,t.status,t.source_reference,t.currency,t.amount,t.billing_months,t.enabled,t.version,
                   f.code AS fee_code,f.label AS fee_label,f.periodicity AS fee_periodicity,
                   c.label AS class_label,s.label AS section_label,
                   CASE t.scope_type WHEN 'SCHOOL' THEN 'Toute l''école'
                        WHEN 'SECTION' THEN s.label
                        WHEN 'ACADEMIC_CLASS' THEN t.scope_ref
                        WHEN 'OPTION_GROUP' THEN CASE t.scope_ref WHEN 'GENERAL' THEN 'Humanités générales'
                             WHEN 'TECHNICAL' THEN 'Humanités techniques' ELSE 'Autre groupe' END
                        ELSE c.label END AS scope_label
              FROM tariffs t JOIN fee_types f ON f.id=t.fee_type_id
              LEFT JOIN school_classes c ON c.id=t.class_id LEFT JOIN school_sections s ON s.id=t.section_id
             WHERE t.school_id=:sid AND (CAST(:year AS uuid) IS NULL OR t.academic_year_id=:year)
             ORDER BY f.label,CASE t.scope_type WHEN 'CLASS' THEN 1 WHEN 'ACADEMIC_CLASS' THEN 2 WHEN 'OPTION_GROUP' THEN 3
                      WHEN 'SECTION' THEN 4 ELSE 5 END,t.effective_from DESC
        """),{"sid":school_id,"year":year_id}).all()
        return [self._tariff_out(r) for r in rows]

    def _editable_year(self, school_id: UUID, year_id: UUID) -> dict[str,Any]:
        row=self.connection.execute(text("SELECT id,code,label,status,start_date,end_date FROM academic_years WHERE id=:id AND school_id=:sid"),
                                    {"id":year_id,"sid":school_id}).first()
        if row is None: raise ValueError("Année scolaire incompatible avec cette école")
        y=dict(_m(row))
        if y['status'] in ('CLOSED','ARCHIVED'): raise ValueError(f"L'année {y['label']} est en lecture seule ({y['status']})")
        return y

    def upsert_tariff_rule(self, school_id: UUID, *, academic_year_id:UUID, fee_type_id:UUID, scope_type:str, scope_ref:str|None,
                           amount:Decimal|None, currency:str, status:str='ACTIVE', effective_from:date|None=None,
                           source_reference:str|None=None) -> tuple[dict[str,Any], dict[str,Any]|None]:
        """Desktop upsert_tariff_rule / save_tariff_group_rule: one rule per (fee, target, effective date); same key = update.
        Returns (rule, previous rule or None)."""
        scope_type=scope_type.strip().upper(); currency=currency.strip().upper(); status=status.strip().upper()
        if scope_type not in self.TARIFF_PRIORITY: raise ValueError("Portée tarifaire invalide")
        if currency not in ('CDF','USD'): raise ValueError("Devise invalide")
        if status not in ('ACTIVE','PENDING_OFFICIAL','INACTIVE'): raise ValueError("Statut tarifaire invalide")
        if status=='ACTIVE' and amount is None: raise ValueError("Un tarif actif doit avoir un montant")
        if amount is not None and amount < 0: raise ValueError("Le montant ne peut pas être négatif")
        year=self._editable_year(school_id,academic_year_id)
        if self.connection.execute(text("SELECT 1 FROM fee_types WHERE id=:id AND school_id=:sid"),{"id":fee_type_id,"sid":school_id}).first() is None:
            raise ValueError("Type de frais introuvable")
        ref=(scope_ref or "").strip()
        class_id=section_id=None
        if scope_type=='SCHOOL':
            ref='*'
        elif not ref:
            raise ValueError("La portée sélectionnée doit préciser sa cible")
        elif scope_type=='SECTION':
            if self.connection.execute(text("SELECT 1 FROM school_sections WHERE id=CAST(:id AS uuid) AND school_id=:sid"),{"id":ref,"sid":school_id}).first() is None:
                raise ValueError("Section incompatible avec cette école")
            section_id=UUID(ref)
        elif scope_type=='CLASS':
            row=self.connection.execute(text("""SELECT section_id FROM school_classes WHERE id=CAST(:id AS uuid) AND school_id=:sid
                AND academic_year_id=:year AND status<>'ARCHIVED'"""),{"id":ref,"sid":school_id,"year":academic_year_id}).first()
            if row is None: raise ValueError("Classe incompatible avec cette école ou cette année")
            class_id=UUID(ref); section_id=_m(row)['section_id']
        elif scope_type=='ACADEMIC_CLASS':
            ref=ref.upper()
            if self.connection.execute(text("""SELECT 1 FROM school_classes WHERE school_id=:sid AND academic_year_id=:year
                AND upper(reference_code)=:ref"""),{"sid":school_id,"year":academic_year_id,"ref":ref}).first() is None:
                raise ValueError("Aucune classe ouverte de ce niveau cette année")
        elif scope_type=='OPTION_GROUP':
            ref=ref.upper()
            if ref not in self.TARIFF_GROUPS: raise ValueError("Groupe tarifaire invalide")
        eff=effective_from or year['start_date']
        if not (year['start_date'] <= eff <= year['end_date']): raise ValueError("La date d'effet doit appartenir à l'année scolaire")
        old=self.connection.execute(text(f"""SELECT {self.TARIFF_COLUMNS} FROM tariffs WHERE school_id=:sid AND academic_year_id=:year
            AND fee_type_id=:fee AND scope_type=:scope AND scope_ref=:ref AND effective_from=:eff AND enabled FOR UPDATE"""),
            {"sid":school_id,"year":academic_year_id,"fee":fee_type_id,"scope":scope_type,"ref":ref,"eff":eff}).first()
        params={"sid":school_id,"year":academic_year_id,"fee":fee_type_id,"scope":scope_type,"ref":ref,"eff":eff,"amount":amount,
                "currency":currency,"status":status,"source":(source_reference or "").strip() or None,"class":class_id,"section":section_id}
        if old is not None:
            row=self.connection.execute(text(f"""UPDATE tariffs SET amount=:amount,currency=:currency,status=:status,source_reference=:source
                WHERE id=:id RETURNING {self.TARIFF_COLUMNS}"""),{**params,"id":_m(old)['id']}).first()
            return self._tariff_out(row), self._tariff_out(old)
        row=self.connection.execute(text(f"""INSERT INTO tariffs(id,school_id,academic_year_id,fee_type_id,class_id,section_id,scope_type,scope_ref,
                effective_from,status,source_reference,currency,amount)
            VALUES (:id,:sid,:year,:fee,:class,:section,:scope,:ref,:eff,:status,:source,:currency,:amount) RETURNING {self.TARIFF_COLUMNS}"""),
            {**params,"id":uuid4()}).first()
        return self._tariff_out(row), None

    def create_tariff(self, school_id: UUID, *, academic_year_id:UUID,fee_type_id:UUID,currency:str,amount:Decimal,
                      class_id:UUID|None=None,section_id:UUID|None=None,option_id:UUID|None=None,
                      billing_months:list[str]|None=None) -> dict[str,Any]:
        """Former Web route kept for compatibility: a class or section tariff from the start of the year."""
        if option_id is not None and class_id is None:
            raise ValueError("Un tarif ne vise pas une option : utilisez le groupe d'Humanités de l'option (Desktop)")
        if class_id is None and section_id is None: raise ValueError("Le tarif doit viser au moins une classe ou une section")
        rule,_old=self.upsert_tariff_rule(school_id,academic_year_id=academic_year_id,fee_type_id=fee_type_id,
                                          scope_type='CLASS' if class_id else 'SECTION',scope_ref=str(class_id or section_id),
                                          amount=amount,currency=currency)
        return rule

    def resolve_tariff(self, school_id: UUID, *, class_id:UUID, fee_type_id:UUID, as_of:date|None=None) -> dict[str,Any]|None:
        """Desktop resolve_tariff_for_class: most precise rule effective at `as_of` (default: end of the class year).
        A rule that is not ACTIVE or has no amount is still returned when it is the most precise one: the caller decides
        (the Desktop skips materialisation of a pending official rule instead of falling back to a less precise one)."""
        cls=self.connection.execute(text("""SELECT c.id,c.academic_year_id,c.section_id,c.reference_code,o.tariff_group_code,y.end_date
              FROM school_classes c JOIN academic_years y ON y.id=c.academic_year_id LEFT JOIN school_options o ON o.id=c.option_id
             WHERE c.id=:id AND c.school_id=:sid"""),{"id":class_id,"sid":school_id}).first()
        if cls is None: raise LookupError("Classe introuvable")
        c=dict(_m(cls)); when=as_of or c['end_date']
        targets=[("CLASS",str(c['id'])),("ACADEMIC_CLASS",(c['reference_code'] or '').upper() or None),
                 ("OPTION_GROUP",c['tariff_group_code']),("SECTION",str(c['section_id'])),("SCHOOL","*")]
        best=None
        for scope,ref in targets:
            if ref is None: continue
            row=self.connection.execute(text(f"""SELECT {self.TARIFF_COLUMNS} FROM tariffs WHERE school_id=:sid AND academic_year_id=:year
                AND fee_type_id=:fee AND scope_type=:scope AND scope_ref=:ref AND enabled AND effective_from<=:when
                ORDER BY effective_from DESC LIMIT 1"""),
                {"sid":school_id,"year":c['academic_year_id'],"fee":fee_type_id,"scope":scope,"ref":ref,"when":when}).first()
            if row is not None:
                item=self._tariff_out(row); item['priority']=self.TARIFF_PRIORITY[scope]
                if best is None or item['priority']>best['priority']: best=item
        return best

    # ---------- monthly billing policy (Desktop monthly_billing_policy) ----------
    MONTHS = ("09","10","11","12","01","02","03","04","05","06","07","08")
    DEFAULT_BILLING_MONTHS = ["09","10","11","12","01","02","03","04","05","06"]

    def get_billing_policy(self, school_id: UUID) -> dict[str,Any]:
        row=self.connection.execute(text("SELECT billing_months,month_due_at_enrollment,version FROM school_billing_policy WHERE school_id=:sid"),
                                    {"sid":school_id}).first()
        if row is None: return {"billing_months":list(self.DEFAULT_BILLING_MONTHS),"month_due_at_enrollment":None,"version":None}
        return dict(_m(row))

    def put_billing_policy(self, school_id: UUID, *, billing_months:list[str], month_due_at_enrollment:str|None,
                           expected_version:int|None) -> tuple[dict[str,Any],dict[str,Any]]:
        months=[]
        for m in billing_months:
            mm=str(m).zfill(2)
            if mm not in self.MONTHS: raise ValueError("Mois de facturation invalide")
            if mm not in months: months.append(mm)
        if not months: raise ValueError("Sélectionnez au moins un mois facturé")
        months=[m for m in self.MONTHS if m in months]  # school-year order
        due=str(month_due_at_enrollment).zfill(2) if month_due_at_enrollment else None
        if due and due not in months: raise ValueError("Le mois exigé à l'inscription doit faire partie des mois facturés")
        old=self.get_billing_policy(school_id)
        if old['version'] is None:
            row=self.connection.execute(text("""INSERT INTO school_billing_policy(school_id,billing_months,month_due_at_enrollment)
                VALUES (:sid,CAST(:m AS jsonb),:due) RETURNING billing_months,month_due_at_enrollment,version"""),
                {"sid":school_id,"m":json.dumps(months),"due":due}).first()
        else:
            if expected_version is None or int(old['version'])!=expected_version:
                raise OptimisticConcurrencyError("Mois de facturation modifiés par une autre session; rechargez")
            row=self.connection.execute(text("""UPDATE school_billing_policy SET billing_months=CAST(:m AS jsonb),month_due_at_enrollment=:due
                WHERE school_id=:sid AND version=:v RETURNING billing_months,month_due_at_enrollment,version"""),
                {"sid":school_id,"m":json.dumps(months),"due":due,"v":expected_version}).first()
            if row is None: raise OptimisticConcurrencyError("Mois de facturation modifiés par une autre session")
        return dict(_m(row)), old

    CLASS_COLUMNS = "id,academic_year_id,section_id,option_id,reference_code,code,label,enabled,status,archived_at,version"

    def _class_for_change(self, school_id: UUID, class_id: UUID) -> dict[str,Any]:
        row=self.connection.execute(text("""SELECT c.id,c.status,c.version,y.status AS year_status,y.label AS year_label
              FROM school_classes c JOIN academic_years y ON y.id=c.academic_year_id
             WHERE c.id=:id AND c.school_id=:sid FOR UPDATE OF c"""),{"id":class_id,"sid":school_id}).first()
        if row is None: raise LookupError("Classe introuvable")
        cls=dict(_m(row))
        # Desktop _ensure_configuration_year_editable: a closed or archived year is read-only.
        if cls['year_status'] in ('CLOSED','ARCHIVED'):
            raise ValueError(f"L'année {cls['year_label']} est en lecture seule : la classe ne peut plus être modifiée")
        return cls

    def update_class(self, school_id: UUID, class_id: UUID, *, code:str, label:str, expected_version:int) -> dict[str,Any]:
        """Rename only (Desktop rename_class). The class state has its own operation and capability."""
        code=code.strip().upper();label=label.strip()
        if not code or not label: raise ValueError("Code et libellé de classe obligatoires")
        if self._class_for_change(school_id,class_id)['status']=='ARCHIVED': raise ValueError("Une classe archivée ne se modifie plus")
        row=self.connection.execute(text(f"""
            UPDATE school_classes SET code=:code,label=:label
             WHERE id=:id AND school_id=:sid AND version=:expected RETURNING {self.CLASS_COLUMNS}
        """),{"id":class_id,"sid":school_id,"code":code,"label":label,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Classe modifiée par une autre session ou introuvable")
        return dict(_m(row))

    def set_class_status(self, school_id: UUID, class_id: UUID, *, status:str, expected_version:int) -> dict[str,Any]:
        """Desktop set_class_status: ACTIVE <-> INACTIVE (pause, students kept), ARCHIVED only when the class is empty."""
        status=status.strip().upper()
        if status not in ('ACTIVE','INACTIVE','ARCHIVED'): raise ValueError("Statut de classe invalide")
        cls=self._class_for_change(school_id,class_id)
        if cls['status']=='ARCHIVED': raise ValueError("Une classe archivée ne change plus de statut")
        if status=='ARCHIVED':
            active=int(self.connection.execute(text(
                "SELECT count(*) FROM enrollments WHERE school_id=:sid AND class_id=:id AND status='VALIDATED'"),{"sid":school_id,"id":class_id}).scalar_one())
            if active: raise ValueError("Une classe contenant des inscriptions actives ne peut pas être archivée")
        row=self.connection.execute(text(f"""
            UPDATE school_classes SET status=CAST(:status AS varchar),enabled=(CAST(:status AS varchar)='ACTIVE'),archived_at=CASE WHEN CAST(:status AS varchar)='ARCHIVED' THEN now() ELSE NULL END
             WHERE id=:id AND school_id=:sid AND version=:expected RETURNING {self.CLASS_COLUMNS}
        """),{"id":class_id,"sid":school_id,"status":status,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Classe modifiée par une autre session ou introuvable")
        return dict(_m(row))

    def update_fee_type(self, school_id: UUID, fee_type_id: UUID, *, label:str, periodicity:str, default_currency:str,
                        regulatory:bool, enabled:bool, expected_version:int) -> dict[str,Any]:
        periodicity=periodicity.upper();currency=default_currency.upper();label=label.strip()
        if periodicity not in {'ONE_TIME','MONTHLY','PERIODIC','OPTIONAL'}: raise ValueError("Périodicité invalide")
        if currency not in {'CDF','USD'}: raise ValueError("Devise invalide")
        row=self.connection.execute(text("""
            UPDATE fee_types SET label=:label,periodicity=:periodicity,default_currency=:currency,regulatory=:regulatory,enabled=:enabled
             WHERE id=:id AND school_id=:sid AND version=:expected
             RETURNING id,code,label,periodicity,default_currency,regulatory,enabled,version
        """),{"id":fee_type_id,"sid":school_id,"label":label,"periodicity":periodicity,"currency":currency,
                 "regulatory":regulatory,"enabled":enabled,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Type de frais modifié par une autre session ou introuvable")
        return dict(_m(row))

    def update_tariff(self, school_id: UUID, tariff_id: UUID, *, currency:str, amount:Decimal, billing_months:list[str],
                      enabled:bool, expected_version:int) -> dict[str,Any]:
        if amount <= 0: raise ValueError("Le tarif doit être strictement positif; une gratuité est une décision financière, pas un tarif zéro")
        currency=currency.upper()
        if currency not in {'CDF','USD'}: raise ValueError("Devise invalide")
        row=self.connection.execute(text("""
            UPDATE tariffs SET currency=:currency,amount=:amount,billing_months=CAST(:months AS jsonb),enabled=:enabled
             WHERE id=:id AND school_id=:sid AND version=:expected
             RETURNING id,academic_year_id,fee_type_id,class_id,section_id,option_id,currency,amount,billing_months,enabled,version
        """),{"id":tariff_id,"sid":school_id,"currency":currency,"amount":amount,"months":json.dumps(billing_months),"enabled":enabled,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Tarif modifié par une autre session ou introuvable")
        out=dict(_m(row));out['amount']=str(out['amount']);return out

    def update_contribution(self, school_id:UUID, contribution_id:UUID, *, label:str,unit:str,enabled:bool,expected_version:int):
        row=self.connection.execute(text("""UPDATE contribution_types SET label=:label,unit=:unit,enabled=:enabled
             WHERE id=:id AND school_id=:sid AND version=:expected RETURNING id,code,label,unit,enabled,version"""),
             {"id":contribution_id,"sid":school_id,"label":label.strip(),"unit":unit.strip() or 'unité',"enabled":enabled,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Contribution modifiée par une autre session ou introuvable")
        return dict(_m(row))

    def update_product(self, school_id:UUID, product_id:UUID, *, label:str,currency:str,unit_price:Decimal,stock_tracking:bool,enabled:bool,expected_version:int):
        if unit_price<=0: raise ValueError("Prix strictement positif requis")
        currency=currency.upper()
        if currency not in {'CDF','USD'}: raise ValueError("Devise invalide")
        row=self.connection.execute(text("""UPDATE school_products SET label=:label,currency=:currency,unit_price=:price,stock_tracking=:tracking,enabled=:enabled
             WHERE id=:id AND school_id=:sid AND version=:expected RETURNING id,code,label,currency,unit_price,stock_tracking,enabled,version"""),
             {"id":product_id,"sid":school_id,"label":label.strip(),"currency":currency,"price":unit_price,"tracking":stock_tracking,"enabled":enabled,"expected":expected_version}).first()
        if row is None: raise OptimisticConcurrencyError("Article modifié par une autre session ou introuvable")
        out=dict(_m(row));out['unit_price']=str(out['unit_price']);return out

    def copy_academic_year_configuration(self, school_id:UUID, *, source_year_id:UUID,target_year_id:UUID) -> dict[str,int]:
        if source_year_id == target_year_id: raise ValueError("Année source et cible doivent être différentes")
        rows=self.connection.execute(text("SELECT id,status FROM academic_years WHERE school_id=:sid AND id IN (:source,:target)"),
                                     {"sid":school_id,"source":source_year_id,"target":target_year_id}).all()
        found={_m(r)['id']:_m(r)['status'] for r in rows}
        if source_year_id not in found or target_year_id not in found: raise ValueError("Année source/cible incompatible avec cette école")
        if found[target_year_id] != 'PREPARED': raise ValueError("La configuration ne peut être copiée que vers une année PREPARED")
        source_classes=self.connection.execute(text("""SELECT section_id,option_id,reference_code,code,label,enabled
            FROM school_classes WHERE school_id=:sid AND academic_year_id=:source ORDER BY code"""),{"sid":school_id,"source":source_year_id}).all()
        class_created=0
        for row in source_classes:
            m=_m(row)
            result=self.connection.execute(text("""INSERT INTO school_classes(id,school_id,academic_year_id,section_id,option_id,reference_code,code,label,enabled,status)
                VALUES(:id,:sid,:target,:section,:option,:ref,:code,:label,:enabled,CASE WHEN :enabled THEN 'ACTIVE' ELSE 'INACTIVE' END)
                ON CONFLICT (school_id,academic_year_id,code) DO NOTHING RETURNING id"""),
                {"id":uuid4(),"sid":school_id,"target":target_year_id,"section":m['section_id'],"option":m['option_id'],"ref":m['reference_code'],"code":m['code'],"label":m['label'],"enabled":m['enabled']}).first()
            if result is not None: class_created += 1
        target_by_code={_m(r)['code']:_m(r)['id'] for r in self.connection.execute(text(
            "SELECT id,code FROM school_classes WHERE school_id=:sid AND academic_year_id=:target"),{"sid":school_id,"target":target_year_id}).all()}
        source_class_codes={_m(r)['id']:_m(r)['code'] for r in self.connection.execute(text(
            "SELECT id,code FROM school_classes WHERE school_id=:sid AND academic_year_id=:source"),{"sid":school_id,"source":source_year_id}).all()}
        # Desktop prepare_year_from_previous: rules are copied with their target and shifted date; an ACTIVE amount becomes
        # PENDING_OFFICIAL in the new year (the school confirms the new scale), other statuses are kept.
        years={_m(r)['id']:_m(r) for r in self.connection.execute(text("SELECT id,start_date,end_date FROM academic_years WHERE school_id=:sid AND id IN (:s,:t)"),
                                                                  {"sid":school_id,"s":source_year_id,"t":target_year_id}).all()}
        target_year=years[target_year_id]
        def shift(value):
            if value is None: return target_year['start_date']
            start=target_year['start_date']; yr=start.year if value.month>=start.month else start.year+1
            try: moved=value.replace(year=yr)
            except ValueError: moved=value.replace(year=yr,day=28)
            return min(max(moved,target_year['start_date']),target_year['end_date'])
        tariffs=self.connection.execute(text("""SELECT fee_type_id,class_id,section_id,scope_type,scope_ref,effective_from,status,source_reference,
                   currency,amount FROM tariffs WHERE school_id=:sid AND academic_year_id=:source AND enabled ORDER BY id"""),
                   {"sid":school_id,"source":source_year_id}).all()
        tariff_created=0
        for row in tariffs:
            m=_m(row);target_class=None;ref=m['scope_ref']
            if m['scope_type']=='CLASS':
                code=source_class_codes.get(m['class_id']);target_class=target_by_code.get(code)
                if target_class is None: continue
                ref=str(target_class)
            result=self.connection.execute(text("""INSERT INTO tariffs(id,school_id,academic_year_id,fee_type_id,class_id,section_id,scope_type,scope_ref,
                    effective_from,status,source_reference,currency,amount)
                VALUES(:id,:sid,:target,:fee,:class,:section,:scope,:ref,:eff,:status,:source,:currency,:amount)
                ON CONFLICT DO NOTHING RETURNING id"""),
                {"id":uuid4(),"sid":school_id,"target":target_year_id,"fee":m['fee_type_id'],"class":target_class,"section":m['section_id'],
                 "scope":m['scope_type'],"ref":ref,"eff":shift(m['effective_from']),
                 "status":'PENDING_OFFICIAL' if m['status']=='ACTIVE' else m['status'],"source":m['source_reference'],
                 "currency":m['currency'],"amount":m['amount']}).first()
            if result is not None: tariff_created += 1
        return {"classes_created":class_created,"tariffs_created":tariff_created}

    # ---------- generic versioned policy documents ----------
    def get_policy(self, school_id: UUID, kind:str) -> dict[str,Any]|None:
        row=self.connection.execute(text("""
            SELECT id,kind,status,payload,effective_from,effective_until,version,updated_at
              FROM school_policy_documents WHERE school_id=:sid AND kind=:kind
        """),{"sid":school_id,"kind":kind.upper()}).first()
        return None if row is None else dict(_m(row))

    def put_policy(self, school_id: UUID, *, kind:str,payload:dict[str,Any],expected_version:int|None=None,
                   status:str='ACTIVE',effective_from:date|None=None,effective_until:date|None=None) -> dict[str,Any]:
        kind=kind.upper(); status=status.upper()
        allowed={'PAYMENT','ENROLLMENT','BENEFITS','DOCUMENTS','BACKUP','COMMUNICATIONS'}
        if kind not in allowed: raise ValueError("Type de politique inconnu")
        current=self.get_policy(school_id,kind)
        if current is None:
            row=self.connection.execute(text("""
                INSERT INTO school_policy_documents(id,school_id,kind,status,payload,effective_from,effective_until)
                VALUES (:id,:sid,:kind,:status,CAST(:payload AS jsonb),:ef,:eu)
                RETURNING id,kind,status,payload,effective_from,effective_until,version,updated_at
            """),{"id":uuid4(),"sid":school_id,"kind":kind,"status":status,"payload":json.dumps(payload,ensure_ascii=False),"ef":effective_from,"eu":effective_until}).first()
        else:
            if expected_version is None or int(current['version']) != expected_version:
                raise OptimisticConcurrencyError("Politique modifiée par une autre session; rechargez")
            row=self.connection.execute(text("""
                UPDATE school_policy_documents SET status=:status,payload=CAST(:payload AS jsonb),effective_from=:ef,effective_until=:eu
                 WHERE school_id=:sid AND kind=:kind AND version=:expected
                 RETURNING id,kind,status,payload,effective_from,effective_until,version,updated_at
            """),{"sid":school_id,"kind":kind,"status":status,"payload":json.dumps(payload,ensure_ascii=False),"ef":effective_from,"eu":effective_until,"expected":expected_version}).first()
            if row is None: raise OptimisticConcurrencyError("Politique modifiée par une autre session")
        return dict(_m(row))

    # ---------- contributions/products ----------
    def list_contributions(self, school_id:UUID):
        return [dict(_m(r)) for r in self.connection.execute(text("SELECT id,code,label,unit,enabled,version FROM contribution_types WHERE school_id=:sid ORDER BY label"),{"sid":school_id}).all()]

    def create_contribution(self, school_id:UUID,*,code:str,label:str,unit:str='unité'):
        r=self.connection.execute(text("""INSERT INTO contribution_types(id,school_id,code,label,unit) VALUES(:id,:sid,:code,:label,:unit)
            RETURNING id,code,label,unit,enabled,version"""),{"id":uuid4(),"sid":school_id,"code":code.strip().upper(),"label":label.strip(),"unit":unit.strip() or 'unité'}).first()
        return dict(_m(r))

    def list_products(self, school_id:UUID):
        rows=self.connection.execute(text("SELECT id,code,label,currency,unit_price,stock_tracking,enabled,version FROM school_products WHERE school_id=:sid ORDER BY label"),{"sid":school_id}).all()
        out=[]
        for r in rows:
            x=dict(_m(r)); x['unit_price']=str(x['unit_price']); out.append(x)
        return out

    def create_product(self, school_id:UUID,*,code:str,label:str,currency:str,unit_price:Decimal,stock_tracking:bool=False):
        if unit_price<=0: raise ValueError("Prix strictement positif requis")
        currency=currency.upper()
        if currency not in {'CDF','USD'}: raise ValueError("Devise invalide")
        r=self.connection.execute(text("""INSERT INTO school_products(id,school_id,code,label,currency,unit_price,stock_tracking)
            VALUES(:id,:sid,:code,:label,:currency,:price,:tracking)
            RETURNING id,code,label,currency,unit_price,stock_tracking,enabled,version"""),{"id":uuid4(),"sid":school_id,"code":code.strip().upper(),"label":label.strip(),"currency":currency,"price":unit_price,"tracking":stock_tracking}).first()
        x=dict(_m(r)); x['unit_price']=str(x['unit_price']); return x
