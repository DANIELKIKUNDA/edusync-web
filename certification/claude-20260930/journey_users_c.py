"""School C (single access manager): a plain member the admin will grant rights to through the UI."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa
C = state["C"]
u = ensure_user(C, "C_MEMBER", ())
print("C member ready", u.get("admin_role_removed"))
