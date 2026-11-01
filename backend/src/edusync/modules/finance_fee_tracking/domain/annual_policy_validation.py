from decimal import Decimal
from edusync.modules.finance_fee_tracking.domain.annual_exigibility import DayBand, EntryPolicy, PriorPeriodMode

def validate_policy_rules(rules):
    if not rules:
        raise ValueError("No fee rules")
    seen = set()
    for rule in rules:
        fee_id = str(rule["fee_type_id"])
        if fee_id in seen:
            raise ValueError("Duplicate fee type")
        seen.add(fee_id)
        bands = tuple(DayBand(int(b["first_day"]), b.get("last_day"), Decimal(str(b["percent"]))) for b in rule["bands"])
        EntryPolicy(PriorPeriodMode(rule["prior_mode"]), bands,
                    Decimal(str(rule["prior_percent"])) if rule.get("prior_percent") is not None else None)
    return len(seen)
