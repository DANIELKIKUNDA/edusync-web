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
            SELECT c.id,c.academic_year_id,c.section_id,c.option_id,c.reference_code,c.code,c.label,c.enabled,c.version,
                   s.code AS section_code,s.label AS section_label,y.code AS academic_year_code
              FROM school_classes c JOIN school_sections s ON s.id=c.section_id JOIN academic_years y ON y.id=c.academic_year_id
             WHERE c.school_id=:sid AND (CAST(:year AS uuid) IS NULL OR c.academic_year_id=:year)
             ORDER BY s.label,c.label
        """),{"sid":school_id,"year":year_id}).all()
        return [dict(_m(r)) for r in rows]

    def create_class(self, school_id: UUID, *, academic_year_id:UUID,section_id:UUID,code:str,label:str,
                     reference_code:str|None=None,option_id:UUID|None=None) -> dict[str,Any]:
        # tenant-consistency checks are explicit; RLS is defence in depth.
        ok=self.connection.execute(text("""
            SELECT 1 FROM academic_years y JOIN school_sections s ON s.school_id=y.school_id
             WHERE y.id=:y AND s.id=:s AND y.school_id=:sid
        """),{"y":academic_year_id,"s":section_id,"sid":school_id}).first()
        if ok is None: raise ValueError("Année/section incompatible avec cette école")
        if option_id is not None:
            option_ok=self.connection.execute(text("""
                SELECT 1 FROM school_options WHERE id=:option AND school_id=:sid AND section_id=:section AND enabled
            """),{"option":option_id,"sid":school_id,"section":section_id}).first()
            if option_ok is None: raise ValueError("Option incompatible avec la section ou cette école")
        r=self.connection.execute(text("""
            INSERT INTO school_classes(id,school_id,academic_year_id,section_id,option_id,reference_code,code,label)
            VALUES (:id,:sid,:y,:section,:option,:ref,:code,:label)
            RETURNING id,academic_year_id,section_id,option_id,reference_code,code,label,enabled,version
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

    def list_tariffs(self, school_id: UUID, year_id: UUID|None=None) -> list[dict[str,Any]]:
        rows=self.connection.execute(text("""
            SELECT t.id,t.academic_year_id,t.fee_type_id,t.class_id,t.section_id,t.option_id,t.currency,t.amount,
                   t.billing_months,t.enabled,t.version,f.code AS fee_code,f.label AS fee_label,
                   c.label AS class_label,s.label AS section_label
              FROM tariffs t JOIN fee_types f ON f.id=t.fee_type_id
              LEFT JOIN school_classes c ON c.id=t.class_id LEFT JOIN school_sections s ON s.id=t.section_id
             WHERE t.school_id=:sid AND (CAST(:year AS uuid) IS NULL OR t.academic_year_id=:year)
             ORDER BY f.label,coalesce(c.label,s.label)
        """),{"sid":school_id,"year":year_id}).all()
        out=[]
        for r in rows:
            x=dict(_m(r)); x['amount']=str(x['amount']); out.append(x)
        return out

    def create_tariff(self, school_id: UUID, *, academic_year_id:UUID,fee_type_id:UUID,currency:str,amount:Decimal,
                      class_id:UUID|None=None,section_id:UUID|None=None,option_id:UUID|None=None,
                      billing_months:list[str]|None=None) -> dict[str,Any]:
        if amount <= 0: raise ValueError("Le tarif doit être strictement positif; une gratuité est une décision financière, pas un tarif zéro")
        currency=currency.upper()
        if currency not in {'CDF','USD'}: raise ValueError("Devise invalide")
        if class_id is None and section_id is None: raise ValueError("Le tarif doit viser au moins une classe ou une section")
        year_ok=self.connection.execute(text("SELECT 1 FROM academic_years WHERE id=:id AND school_id=:sid"),{"id":academic_year_id,"sid":school_id}).first()
        fee_ok=self.connection.execute(text("SELECT 1 FROM fee_types WHERE id=:id AND school_id=:sid AND enabled"),{"id":fee_type_id,"sid":school_id}).first()
        if year_ok is None or fee_ok is None: raise ValueError("Année ou type de frais incompatible avec cette école")
        if section_id is not None:
            section_ok=self.connection.execute(text("SELECT 1 FROM school_sections WHERE id=:id AND school_id=:sid AND enabled"),{"id":section_id,"sid":school_id}).first()
            if section_ok is None: raise ValueError("Section incompatible avec cette école")
        if class_id is not None:
            class_ok=self.connection.execute(text("""SELECT section_id,option_id FROM school_classes
                WHERE id=:id AND school_id=:sid AND academic_year_id=:year AND enabled"""),{"id":class_id,"sid":school_id,"year":academic_year_id}).first()
            if class_ok is None: raise ValueError("Classe incompatible avec cette école ou cette année")
            cm=_m(class_ok)
            if section_id is not None and cm['section_id'] != section_id: raise ValueError("La classe ne correspond pas à la section du tarif")
            if option_id is not None and cm['option_id'] not in {None,option_id}: raise ValueError("La classe ne correspond pas à l'option du tarif")
        if option_id is not None:
            option_ok=self.connection.execute(text("SELECT section_id FROM school_options WHERE id=:id AND school_id=:sid AND enabled"),{"id":option_id,"sid":school_id}).first()
            if option_ok is None: raise ValueError("Option incompatible avec cette école")
            if section_id is not None and _m(option_ok)['section_id'] != section_id: raise ValueError("L'option ne correspond pas à la section du tarif")
        r=self.connection.execute(text("""
            INSERT INTO tariffs(id,school_id,academic_year_id,fee_type_id,class_id,section_id,option_id,currency,amount,billing_months)
            VALUES (:id,:sid,:year,:fee,:class,:section,:option,:currency,:amount,CAST(:months AS jsonb))
            RETURNING id,academic_year_id,fee_type_id,class_id,section_id,option_id,currency,amount,billing_months,enabled,version
        """),{"id":uuid4(),"sid":school_id,"year":academic_year_id,"fee":fee_type_id,"class":class_id,"section":section_id,
                 "option":option_id,"currency":currency,"amount":amount,"months":json.dumps(billing_months or [])}).first()
        x=dict(_m(r)); x['amount']=str(x['amount']); return x

    def update_class(self, school_id: UUID, class_id: UUID, *, code:str, label:str, enabled:bool, expected_version:int) -> dict[str,Any]:
        code=code.strip().upper();label=label.strip()
        if not code or not label: raise ValueError("Code et libellé de classe obligatoires")
        row=self.connection.execute(text("""
            UPDATE school_classes SET code=:code,label=:label,enabled=:enabled
             WHERE id=:id AND school_id=:sid AND version=:expected
             RETURNING id,academic_year_id,section_id,option_id,reference_code,code,label,enabled,version
        """),{"id":class_id,"sid":school_id,"code":code,"label":label,"enabled":enabled,"expected":expected_version}).first()
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
            result=self.connection.execute(text("""INSERT INTO school_classes(id,school_id,academic_year_id,section_id,option_id,reference_code,code,label,enabled)
                VALUES(:id,:sid,:target,:section,:option,:ref,:code,:label,:enabled)
                ON CONFLICT (school_id,academic_year_id,code) DO NOTHING RETURNING id"""),
                {"id":uuid4(),"sid":school_id,"target":target_year_id,"section":m['section_id'],"option":m['option_id'],"ref":m['reference_code'],"code":m['code'],"label":m['label'],"enabled":m['enabled']}).first()
            if result is not None: class_created += 1
        target_by_code={_m(r)['code']:_m(r)['id'] for r in self.connection.execute(text(
            "SELECT id,code FROM school_classes WHERE school_id=:sid AND academic_year_id=:target"),{"sid":school_id,"target":target_year_id}).all()}
        source_class_codes={_m(r)['id']:_m(r)['code'] for r in self.connection.execute(text(
            "SELECT id,code FROM school_classes WHERE school_id=:sid AND academic_year_id=:source"),{"sid":school_id,"source":source_year_id}).all()}
        tariffs=self.connection.execute(text("""SELECT fee_type_id,class_id,section_id,option_id,currency,amount,billing_months,enabled
            FROM tariffs WHERE school_id=:sid AND academic_year_id=:source ORDER BY id"""),{"sid":school_id,"source":source_year_id}).all()
        tariff_created=0
        for row in tariffs:
            m=_m(row);target_class=None
            if m['class_id'] is not None:
                code=source_class_codes.get(m['class_id']);target_class=target_by_code.get(code)
                if target_class is None: continue
            result=self.connection.execute(text("""INSERT INTO tariffs(id,school_id,academic_year_id,fee_type_id,class_id,section_id,option_id,currency,amount,billing_months,enabled)
                VALUES(:id,:sid,:target,:fee,:class,:section,:option,:currency,:amount,CAST(:months AS jsonb),:enabled)
                ON CONFLICT DO NOTHING RETURNING id"""),
                {"id":uuid4(),"sid":school_id,"target":target_year_id,"fee":m['fee_type_id'],"class":target_class,
                 "section":m['section_id'],"option":m['option_id'],"currency":m['currency'],"amount":m['amount'],
                 "months":json.dumps(m['billing_months']),"enabled":m['enabled']}).first()
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
