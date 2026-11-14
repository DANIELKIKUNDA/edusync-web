"""Validate annual fee rules before persistence or activation."""
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
        bands = tuple(
            DayBand(int(b["first_day"]),
                    int(b["last_day"]) if b.get("last_day") is not None else None,
                    Decimal(str(b["percent"])))
            for b in rule["bands"]
        )
        EntryPolicy(
            PriorPeriodMode(rule["prior_mode"]), bands,
            Decimal(str(rule["prior_percent"])) if rule.get("prior_percent") is not None else None,
        )
    return len(seen)


# Messages shown to a school administrator: one French catalogue for the whole API (edusync.shared.user_messages).
def french_policy_error(exc: Exception) -> ValueError:
    """The same error, worded for the school administrator."""
    from edusync.shared.user_messages import to_french
    return ValueError(to_french(str(exc)))
