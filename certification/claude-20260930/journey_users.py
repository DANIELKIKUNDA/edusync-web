"""Journey accounts: each holds ONLY its business role (bootstrap ADMIN role removed by ensure_user)."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
A = state["A"]
for key, role in (("UI_CASH", "CAISSIER"), ("UI_GEST", "GESTIONNAIRE"), ("UI_SECR", "SECRETARIAT"), ("UI_PROMO", "PROMOTEUR"), ("UI_INT", "INTENDANT")):
    u = ensure_user(A, key, (role,))
    perms = must(user_client(A, key), "GET", "auth/me").json()["permissions"]
    print(key, role, "admin_removed=", u.get("admin_role_removed"), "access.roles.manage" in perms, len(perms))
