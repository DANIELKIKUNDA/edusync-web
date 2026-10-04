"""Staff exit must revoke the linked access account (tenant role, real PostgreSQL, real HTTP)."""
import sys
from uuid import uuid4
sys.path.insert(0, __import__("os").path.dirname(__file__))
from common import *  # noqa

A = state["A"]
grant_test_role(A, "ADMIN", "CL_PERSONNEL", ("personnel.create", "personnel.exit", "personnel.read"))
A["users"].pop("LEAVER", None)
ensure_user(A, "LEAVER", ("CAISSIER",))
adm = user_client(A, "ADMIN")
r = must(adm, "POST", "personnel", 201, json={"employee_no": "EMP-" + uuid4().hex[:6], "last_name": "SORTANT", "first_name": "Agent", "category": "AUTRE"})
staff = r.json()
lv = A["users"]["LEAVER"]
r = call(adm, "POST", f"personnel/{staff['id']}/access-links", json={"membership_id": lv["membership_id"], "reason": "Compte de l'agent"})
check("link staff to access account", r.status_code in (200, 201), f"HTTP {r.status_code} {r.text[:150]}")
leaver = user_client(A, "LEAVER")
check("linked user can use API before exit", call(leaver, "GET", "auth/me").status_code == 200)
staff = must(adm, "GET", f"personnel/{staff['id']}").json()
ver = staff.get("version") or staff.get("staff", {}).get("version")
r = call(adm, "POST", f"personnel/{staff.get('id') or staff['staff']['id']}/exit", json={"reason": "Fin de contrat recette"}, headers={"If-Match": str(ver)})
check("staff exit with linked access succeeds", r.status_code == 200, f"HTTP {r.status_code} {r.text[:150]}")
active = sql("SELECT active FROM school_memberships WHERE id=:m", {"m": lv["membership_id"]})[0]["active"]
check("linked membership deactivated after exit", active is False, f"active={active}")
r = call(leaver, "GET", "auth/me")
check("existing access token of exited agent rejected", r.status_code in (401, 403), f"HTTP {r.status_code}")
r = call(httpx.Client(base_url=BASE + "/"), "POST", "auth/login", json={"email": lv["email"], "password": lv["password"], "scope": "SCHOOL", "school_code": A["code"]})
check("exited agent cannot log in again", r.status_code in (401, 403), f"HTTP {r.status_code}")

# Boundary: the tenant role may only DEACTIVATE memberships of its own school.
from uuid import UUID
from sqlalchemy import text as _t
from edusync.bootstrap.settings import Settings
from edusync.shared.infrastructure.postgres import DatabaseRuntime
tdb = DatabaseRuntime.from_url(Settings().tenant_database_url, role_kind="tenant")
results_before = len(results)


def tenant_try(school_id, stmt, params):
    try:
        with tdb.tenant_transaction(school_id=UUID(school_id)) as c:
            return ("OK", c.execute(_t(stmt), params).rowcount)
    except Exception as e:  # noqa: BLE001
        return (type(e).__name__, str(e).splitlines()[0][:100])


r = tenant_try(A["school_id"], "UPDATE school_memberships SET active=true WHERE id=:m", {"m": lv["membership_id"]})
check("tenant role cannot reactivate a membership (RESTRICTIVE policy)", r[0] != "OK", str(r))
B = state["B"]
r = tenant_try(A["school_id"], "UPDATE school_memberships SET active=false WHERE id=:m", {"m": B["users"]["CAISSIER1"]["membership_id"]})
check("tenant role of A cannot deactivate a membership of B", r == ("OK", 0) or r[0] != "OK", str(r))
active_b = sql("SELECT active FROM school_memberships WHERE id=:m", {"m": B["users"]["CAISSIER1"]["membership_id"]})[0]["active"]
check("B membership still active", active_b is True)
r = tenant_try(A["school_id"], "UPDATE school_memberships SET school_id=:s WHERE id=:m", {"s": B["school_id"], "m": A["users"]["CAISSIER1"]["membership_id"]})
check("tenant role cannot move a membership to another school", r[0] != "OK", str(r))
dump("personnel-access-live.json")
