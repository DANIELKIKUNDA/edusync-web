"""What is still owed on a charge, the same everywhere (owner, 2026-11-16).

The alerts compared the net amount with the cash paid only, so a month settled outside the cash desk — payments taken over
from the previous system, regularizations — or exempted by a decision still looked unpaid: after the APN import every class
was « en risque financier » although most pupils had paid. Remaining = net − decisions − cash paid − outside-cash settlements
(the payroll deductions of staff children already raise the paid amount).
"""


def still_owed(alias: str = "fc") -> str:
    """SQL expression of the amount still owed on the finance_charges row `alias`."""
    return (f"({alias}.net_amount - {alias}.paid_amount - finance_charge_decision_amount({alias}.id)"
            f" - coalesce((SELECT sum(rg.amount) FROM finance_charge_regularizations rg"
            f" WHERE rg.school_id={alias}.school_id AND rg.charge_id={alias}.id),0))")
