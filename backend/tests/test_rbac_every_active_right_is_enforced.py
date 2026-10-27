"""Security invariant (Gestionnaire certification 2026-10-26): every ACTIVE capability granted to a standard role is
checked by the backend somewhere (need / require / permission test). A right that no route checks protects nothing and
misleads the access screens. Computed from the canonical registry, for every standard role, not a hand-written list."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
CAPS = {c["code"]: c for c in REG["capabilities"]}
BACKEND = "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in (ROOT / "backend/src").rglob("*.py"))


def _checked(code: str) -> bool:
    return re.search(r"['\"]" + re.escape(code) + r"['\"]", BACKEND) is not None


def test_every_active_capability_of_a_standard_role_is_checked_by_the_backend():
    missing = sorted({c for role in REG["standard_roles"].values() for c in role["capabilities"]
                      if CAPS.get(c, {}).get("lifecycle") == "ACTIVE" and not _checked(c)})
    assert missing == [], f"droits actifs qu'aucune route ne contrôle : {missing}"


def test_gestionnaire_keeps_personnel_management_owner_decision_2026_10_26():
    g = set(REG["standard_roles"]["GESTIONNAIRE"]["capabilities"])
    assert {"personnel.create", "personnel.update", "personnel.exit", "personnel.assignments.add", "personnel.assignments.end", "personnel.functions.manage"} <= g
    # supervision without cash-desk operations: no collecting, no own cash session, no enrolling, no settings change
    assert not g & {"finance.checkout.collect", "finance.cash.open", "finance.cash.close", "enrollments.create", "settings.school_identity.update"}
    assert {"finance.cash.other.read", "finance.payments.reverse.supervisor", "finance.reports.periodic.generate"} <= g
    # owner decision 2026-10-27: a chief, not a permanent operator — he does not close / reopen the cashiers' day
    assert not g & {"finance.cash.day.close", "finance.cash.reopen"}
