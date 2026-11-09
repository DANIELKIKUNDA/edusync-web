"""Gestionnaire certification (2026-10-27) — behaviour of the REAL routes for the capabilities that had no dedicated test.

For each capability: the route that checks it is found by introspecting the application (no hand-copied path), its
required path / query parameters are filled, then it is called twice through FastAPI with the school actor replaced:
  * with every Gestionnaire right EXCEPT this one  → 403, and the refusal names the capability;
  * with every Gestionnaire right                  → the permission check passes (any status but 403).
The authorization runs before any database access, so this needs no database.
"""
from __future__ import annotations

import inspect
import re
import json
from datetime import date
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from edusync.bootstrap.app import create_app
from edusync.bootstrap.dependencies import require_school_actor
from edusync.shared.application.context import ActorContext

ROOT = Path(__file__).resolve().parents[2]
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
GEST = frozenset(REG["standard_roles"]["GESTIONNAIRE"]["capabilities"])
CAPS = [
    "audit.school.filter", "communications.history.read", "communications.read", "contributions.read", "documents.open",
    "families.directory.export", "families.read", "finance.analysis.advance.read", "finance.old_debt.read", "finance.products.read",
    "finance.products.sales_report.read", "finance.reports.daily.generate", "finance.reports.periodic.export", "finance.views.vf01.export",
    "inventory.assets.history.read", "inventory.stock.movements.read", "settings.documents.read",
    "students.account.export", "students.account.read", "students.directory.export",
]
# Capabilities checked only for a variant of the call (the audit filter is required only when a filter is used).
EXTRA_QUERY = {"audit.school.filter": {"action": "LOGIN"}}
APP = create_app()
with TestClient(APP):                                   # routes are attached at application startup
    pass


def _all_routes():
    """(full path, APIRoute) — FastAPI groups included routers; walk them with their prefix."""
    out = []
    def walk(routes, prefix=""):
        for r in routes:
            if isinstance(r, APIRoute):
                out.append((prefix + r.path, r))
            elif type(r).__name__ == "_IncludedRouter":
                walk(r.original_router.routes, prefix + (getattr(r.include_context, "prefix", "") or ""))
    walk(APP.routes)
    return out


ROUTES = _all_routes()


def _guarded_routes(cap: str) -> list[tuple[str, APIRoute]]:
    out = []
    for path, r in ROUTES:
        try:
            src = inspect.getsource(r.endpoint)
        except (OSError, TypeError):
            continue
        # the route CHECKS the capability (not merely mentions it in a list); _need_* are scope-aware guards
        if re.search(r"(?:need|require|_need_[a-z_]+)\(\s*(?:actor\s*,\s*)?['\"]" + re.escape(cap) + r"['\"]", src):
            out.append((path, r))
    return sorted(out, key=lambda pr: (0 if "GET" in pr[1].methods else 1, pr[0]))


def _value(annotation, name: str):
    t = str(annotation)
    if "UUID" in t: return str(uuid4())
    if "date" in t: return date(2026, 10, 1).isoformat()
    if "int" in t: return 1
    if "bool" in t: return "false"
    if name in ("period_type",): return "MENSUEL"
    if name in ("profile_code",): return "CONSOLIDE"
    if name in ("currency",): return "CDF"
    return "x"


def _call(client: TestClient, guarded: tuple[str, APIRoute], cap: str = ""):
    path, route = guarded
    for p in route.dependant.path_params:
        path = path.replace("{" + p.name + "}", str(_value(p.field_info.annotation, p.name)))
    query = {q.name: _value(q.field_info.annotation, q.name) for q in route.dependant.query_params if q.field_info.is_required()}
    query.update(EXTRA_QUERY.get(cap, {}))
    method = "GET" if "GET" in route.methods else sorted(route.methods)[0]
    return client.request(method, path, params=query, json={} if method != "GET" else None, headers={"Idempotency-Key": str(uuid4()), "If-Match": "1"})


def _client(perms: frozenset[str]) -> TestClient:
    actor = ActorContext(user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(), permissions=perms)
    APP.dependency_overrides[require_school_actor] = lambda: actor
    return TestClient(APP, raise_server_exceptions=False)


@pytest.mark.parametrize("cap", CAPS)
def test_capability_is_held_by_the_gestionnaire_and_guards_a_real_route(cap):
    assert cap in GEST, f"{cap} n'est plus un droit du Gestionnaire"
    assert _guarded_routes(cap), f"aucune route ne contrôle {cap}"


@pytest.mark.parametrize("cap", CAPS)
def test_without_the_capability_the_route_is_refused(cap):
    guarded = _guarded_routes(cap)[0]
    with _client(GEST - {cap}) as client:
        r = _call(client, guarded, cap)
    assert r.status_code == 403, f"{guarded[0]} sans {cap} → {r.status_code}"
    assert cap in r.text, f"le refus de {guarded[0]} ne nomme pas {cap} : {r.text[:160]}"


@pytest.mark.parametrize("cap", CAPS)
def test_with_the_gestionnaire_rights_the_permission_check_passes(cap):
    guarded = _guarded_routes(cap)[0]
    with _client(GEST) as client:
        r = _call(client, guarded, cap)
    assert r.status_code != 403 or cap not in r.text, f"{guarded[0]} refusé au Gestionnaire : {r.text[:160]}"
