"""Before each UI journey run: a fresh one-off charge for pupil ELV-00001 so the cashier journey is repeatable.
(Charges are a fixture: the application has no tariff-to-charge generation yet — see report.)"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
A = state["A"]
eid = A["family"]["enrollment_ids"][0]
sql("UPDATE finance_charges SET status='CANCELLED' WHERE enrollment_id=:e AND label='Frais de parcours UI' AND status='ACTIVE' AND paid_amount=0", {"e": eid})
# A charge already partly paid by a previous run stays ACTIVE (ledger is append-only): rename it so the
# journey always targets exactly one 'Frais de parcours UI' line (two identical labels made the probe ambiguous).
sql("UPDATE finance_charges SET label='Passage précédent (parcours UI)' WHERE enrollment_id=:e AND label='Frais de parcours UI' AND status='ACTIVE'", {"e": eid})
sql("INSERT INTO finance_charges(school_id,enrollment_id,label,currency,net_amount,periodicity) VALUES(:s,:e,'Frais de parcours UI','CDF',100000,'ONE_OFF')",
    {"s": A["school_id"], "e": eid})
print("journey charge ready")
