"""Transactional activation of a validated annual finance policy."""
from decimal import Decimal
from sqlalchemy import text
from edusync.modules.finance_fee_tracking.domain.annual_policy_validation import validate_policy_rules


def activate_annual_policy(connection, *, school_id, academic_year_id, policy_id, actor_id):
    # Serialize competing activations using the shared school/year row.
    year = connection.execute(text("""
        SELECT id FROM academic_years WHERE id=:y AND school_id=:s FOR UPDATE
    """), {"y": academic_year_id, "s": school_id}).first()
    if year is None:
        raise ValueError("Academic year not found")
    draft = connection.execute(text("""
        SELECT id FROM finance_exigibility_policies
        WHERE id=:p AND school_id=:s AND academic_year_id=:y AND status='DRAFT'
        FOR UPDATE
    """), {"p": policy_id, "s": school_id, "y": academic_year_id}).first()
    if draft is None:
        raise ValueError("Draft policy not found")
    rows = connection.execute(text("""
        SELECT r.id, r.fee_type_id, r.prior_mode, r.prior_percent
        FROM finance_exigibility_rules r
        WHERE r.school_id=:s AND r.policy_id=:p FOR UPDATE
    """), {"s": school_id, "p": policy_id}).mappings().all()
    rules = []
    for row in rows:
        bands = connection.execute(text("""
            SELECT first_day,last_day,percent FROM finance_exigibility_day_bands
            WHERE school_id=:s AND rule_id=:r ORDER BY first_day
        """), {"s": school_id, "r": row["id"]}).mappings().all()
        rules.append({**dict(row), "bands": [dict(b) for b in bands]})
    count = validate_policy_rules(rules)
    connection.execute(text("""
        UPDATE finance_exigibility_policies SET status='SUPERSEDED'
        WHERE school_id=:s AND academic_year_id=:y AND status='ACTIVE'
    """), {"s": school_id, "y": academic_year_id})
    connection.execute(text("""
        UPDATE finance_exigibility_policies
        SET status='ACTIVE',approved_by=:actor,approved_at=now()
        WHERE id=:p AND school_id=:s AND academic_year_id=:y
    """), {"p": policy_id, "s": school_id, "y": academic_year_id, "actor": actor_id})
    # Caller owns the transaction; no implicit commit. No charge mutations.
    return {"policy_id": str(policy_id), "rules_validated": count, "status": "ACTIVE"}
