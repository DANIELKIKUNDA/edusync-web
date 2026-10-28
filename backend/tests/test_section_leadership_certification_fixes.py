"""PR #27 certification (2026-10-27) — regressions found while signing in as Préfet / Directeur / Directrice."""
from __future__ import annotations

import inspect
from contextlib import contextmanager
from types import SimpleNamespace
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from edusync.bootstrap.dependencies import get_services, require_school_actor
from edusync.modules.access.api import router as access_router
from edusync.modules.access.application.projection import widgets
from edusync.shared.application.context import ActorContext

SECTION_CAPS = {"finance.reports.history.read", "documents.history.read", "headcounts.read"}


def test_school_wide_cards_are_not_offered_to_a_section_only_actor():
    # The home called /finance/reports/generated and /documents/history, which refuse a section-only grant (403).
    ids = {w["id"] for w in widgets(SECTION_CAPS, school_caps=set())}
    assert "reports.latest" not in ids and "documents.recent" not in ids and "headcounts.summary" in ids
    ids = {w["id"] for w in widgets(SECTION_CAPS, school_caps=SECTION_CAPS)}
    assert {"reports.latest", "documents.recent"} <= ids
    assert all("school_scope" not in w for w in widgets(SECTION_CAPS))


def test_access_me_passes_the_school_scoped_capabilities():
    src = inspect.getsource(access_router)
    assert 'projection.widgets(caps, {c for c, t, _ in actor.capability_scopes if t == "SCHOOL"})' in src


def test_section_bound_leadership_roles_are_never_granted_on_the_whole_school():
    # « Ajouter un membre » used to insert a SCHOOL scope for every role: a Directeur de section saw the whole school,
    # a Préfet hit the database trigger (HTTP 500).
    assert access_router.SECTION_BOUND_ROLES == {"PREFET_ETUDES", "DIRECTEUR_ETUDES", "DIRECTEUR_DISCIPLINE", "DIRECTION_SECTION"}
    assert access_router._section_bound({"kind": "SCHOOL_STANDARD", "code": "DIRECTION_SECTION"})
    assert not access_router._section_bound({"kind": "SCHOOL_CUSTOM", "code": "DIRECTION_SECTION"})
    assert not access_router._section_bound({"kind": "SCHOOL_STANDARD", "code": "GESTIONNAIRE"})
    create = inspect.getsource(access_router.create_member)
    assigned = inspect.getsource(access_router._assign_core)
    for src in (create, assigned):
        assert "_section_bound(role)" in src
        assert "jamais sur toute l’école" in src or "choisissez sa ou ses sections" in src
    # section codes are checked in a tenant transaction (the platform connection cannot read school_sections)
    assert "services.tenant_db.tenant_transaction" in create and "VALUES(:a,'SCHOOL',NULL)" not in create


def test_section_only_document_history_is_empty_with_a_reason_not_an_error():
    from edusync.modules.documents.api.router import router

    app = FastAPI(); app.include_router(router, prefix="/documents")
    touched = []

    @contextmanager
    def transaction(**kwargs):
        touched.append(kwargs); yield object()

    actor = ActorContext(user_id=uuid4(), school_id=uuid4(), membership_id=uuid4(), permissions=frozenset({"documents.history.read"}),
                         capability_scopes=(("documents.history.read", "SECTION", "PRIMAIRE"),))
    app.dependency_overrides[require_school_actor] = lambda: actor
    app.dependency_overrides[get_services] = lambda: SimpleNamespace(tenant_db=SimpleNamespace(tenant_transaction=transaction))
    with TestClient(app) as client:
        for scope in ("mine", "school"):
            r = client.get("/documents/history", params={"scope": scope})
            assert r.status_code == 200 and r.json()["items"] == [] and "provenance" in r.json()["restricted"]
    assert touched == []   # fail closed: no archive query at all
