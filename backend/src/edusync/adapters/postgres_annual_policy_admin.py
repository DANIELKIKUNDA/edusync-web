"""School-scoped administration of versioned annual exigibility policies."""
from __future__ import annotations

from uuid import uuid4
from sqlalchemy import text


class PostgresAnnualPolicyAdminRepository:
    def __init__(self, connection):
        self.c = connection

    def list(self, school_id, academic_year_id):
        rows = self.c.execute(text("""SELECT p.id,p.version,p.status,p.effective_from,p.approved_at,p.created_at,
               count(r.id) AS rule_count
          FROM finance_exigibility_policies p
          LEFT JOIN finance_exigibility_rules r ON r.policy_id=p.id AND r.school_id=p.school_id
         WHERE p.school_id=:s AND p.academic_year_id=:y
         GROUP BY p.id ORDER BY p.version DESC"""), {"s": school_id, "y": academic_year_id}).mappings().all()
        return [dict(r) for r in rows]

    def detail(self, school_id, policy_id):
        policy = self.c.execute(text("""SELECT * FROM finance_exigibility_policies
          WHERE school_id=:s AND id=:p"""), {"s": school_id, "p": policy_id}).mappings().one_or_none()
        if policy is None:
            raise LookupError("Politique financière introuvable")
        rules = self.c.execute(text("""SELECT r.id,r.fee_type_id,f.code AS fee_code,f.label AS fee_label,
               r.prior_mode,r.prior_percent
          FROM finance_exigibility_rules r JOIN fee_types f ON f.id=r.fee_type_id AND f.school_id=r.school_id
         WHERE r.school_id=:s AND r.policy_id=:p ORDER BY f.label"""), {"s": school_id, "p": policy_id}).mappings().all()
        out = []
        for rule in rules:
            bands = self.c.execute(text("""SELECT first_day,last_day,percent
              FROM finance_exigibility_day_bands WHERE school_id=:s AND rule_id=:r ORDER BY first_day"""),
                {"s": school_id, "r": rule["id"]}).mappings().all()
            out.append({**dict(rule), "bands": [dict(b) for b in bands]})
        return {**dict(policy), "rules": out}

    def create_draft(self, school_id, academic_year_id, effective_from, actor_id, source_policy_id=None):
        self.c.execute(text("SELECT id FROM academic_years WHERE id=:y AND school_id=:s FOR UPDATE"),
                       {"y": academic_year_id, "s": school_id}).one()
        version = self.c.execute(text("""SELECT COALESCE(max(version),0)+1 FROM finance_exigibility_policies
          WHERE school_id=:s AND academic_year_id=:y"""), {"s": school_id, "y": academic_year_id}).scalar_one()
        policy_id = uuid4()
        self.c.execute(text("""INSERT INTO finance_exigibility_policies
          (id,school_id,academic_year_id,version,status,effective_from,created_by)
          VALUES (:id,:s,:y,:v,'DRAFT',:d,:a)"""),
          {"id": policy_id, "s": school_id, "y": academic_year_id, "v": version, "d": effective_from, "a": actor_id})
        if source_policy_id:
            source = self.detail(school_id, source_policy_id)
            for rule in source["rules"]:
                self.put_rule(school_id, policy_id, rule["fee_type_id"], rule["prior_mode"],
                              rule["prior_percent"], rule["bands"])
        return self.detail(school_id, policy_id)

    def put_rule(self, school_id, policy_id, fee_type_id, prior_mode, prior_percent, bands):
        draft = self.c.execute(text("""SELECT 1 FROM finance_exigibility_policies
          WHERE id=:p AND school_id=:s AND status='DRAFT' FOR UPDATE"""), {"p": policy_id, "s": school_id}).first()
        if draft is None:
            raise ValueError("Seule une politique en brouillon peut être modifiée")
        rule_id = self.c.execute(text("""SELECT id FROM finance_exigibility_rules
          WHERE school_id=:s AND policy_id=:p AND fee_type_id=:f"""),
          {"s": school_id, "p": policy_id, "f": fee_type_id}).scalar_one_or_none() or uuid4()
        self.c.execute(text("""INSERT INTO finance_exigibility_rules
          (id,school_id,policy_id,fee_type_id,prior_mode,prior_percent)
          VALUES (:id,:s,:p,:f,:m,:pct)
          ON CONFLICT(policy_id,fee_type_id) DO UPDATE SET prior_mode=excluded.prior_mode,prior_percent=excluded.prior_percent"""),
          {"id": rule_id, "s": school_id, "p": policy_id, "f": fee_type_id, "m": prior_mode, "pct": prior_percent})
        self.c.execute(text("DELETE FROM finance_exigibility_day_bands WHERE school_id=:s AND rule_id=:r"),
                       {"s": school_id, "r": rule_id})
        for band in bands:
            self.c.execute(text("""INSERT INTO finance_exigibility_day_bands
              (school_id,rule_id,first_day,last_day,percent) VALUES (:s,:r,:first,:last,:pct)"""),
              {"s": school_id, "r": rule_id, "first": band["first_day"], "last": band.get("last_day"), "pct": band["percent"]})
        return self.detail(school_id, policy_id)
