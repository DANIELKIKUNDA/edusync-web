"""Owner decision 2026-10-02 verified live: standard GESTIONNAIRE / SECRETARIAT personnel rights."""
import os
import sys
from uuid import uuid4

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A = state["A"]
for k in ("GEST", "SECR"):
    A["users"].pop(k, None)
ensure_user(A, "GEST", ("GESTIONNAIRE",))
ensure_user(A, "SECR", ("SECRETARIAT",))
g, s = user_client(A, "GEST"), user_client(A, "SECR")


def new_staff(client):
    return call(client, "POST", "personnel", json={"employee_no": "EMP-" + uuid4().hex[:6], "last_name": "AGENT", "first_name": "Decision", "category": "AUTRE"})


r = new_staff(g)
check("GESTIONNAIRE can add an agent", r.status_code == 201, f"HTTP {r.status_code}")
staff = r.json()
r = call(g, "POST", f"personnel/{staff['id']}/exit", json={"reason": "Fin de contrat"}, headers={"If-Match": str(staff["version"])})
check("GESTIONNAIRE can record a departure", r.status_code == 200, f"HTTP {r.status_code} {r.text[:100]}")
r = call(g, "POST", f"personnel/{staff['id']}/reactivate", json={"reason": "Retour"}, headers={"If-Match": str(r.json().get("version", 2))})
check("GESTIONNAIRE cannot reactivate (custom-role only)", r.status_code == 403, f"HTTP {r.status_code}")
r = new_staff(s)
check("SECRETARIAT can add an agent", r.status_code == 201, f"HTTP {r.status_code}")
st2 = r.json()
r = call(s, "POST", f"personnel/{st2['id']}/exit", json={"reason": "Tentative"}, headers={"If-Match": str(st2["version"])})
check("SECRETARIAT cannot record a departure", r.status_code == 403, f"HTTP {r.status_code}")
for code in ("PROMOTEUR", "RESPONSABLE_FINANCE"):
    A["users"].pop("R_" + code, None)
    ensure_user(A, "R_" + code, (code,))
    check(f"{code} still cannot add an agent", new_staff(user_client(A, "R_" + code)).status_code == 403)
dump("personnel-roles-live.json")
