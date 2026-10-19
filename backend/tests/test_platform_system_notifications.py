"""Notifications système (lot 2026-10): contracts. Live behaviour (exact recipients for each target, deduplication,
zero recipient, reconfirmation, idempotency under concurrency, snapshot, expiry, time zone, recipient inbox, history,
volume) is proven by tools/local/notifications_probe.py against a real database."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from edusync.modules.notifications_center.api.router import CampaignInput, _audience

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/notifications_center/api/router.py").read_text(encoding="utf-8")
UI = (ROOT / "frontend/src/platform/campaigns.tsx").read_text(encoding="utf-8")
API = (ROOT / "frontend/src/platform/campaigns_api.ts").read_text(encoding="utf-8")
T = {"type": "PLATFORM_ALL", "school_ids": [], "role_code": None, "user_id": None}


def fn(name: str) -> str:
    start = ROUTER.index(f"def {name}(")
    nxt = ROUTER.find("\n@router", start)
    return ROUTER[start:nxt if nxt > 0 else len(ROUTER)]


@pytest.mark.parametrize("field,value", [("title", "   "), ("body", " \n "), ("title", "x" * 181), ("body", "x" * 2001), ("severity", "URGENT")])
def test_content_validation_never_truncates(field, value):
    with pytest.raises(ValidationError):
        CampaignInput(**{"title": "Titre", "body": "Message", "target": T, field: value})


def test_message_line_breaks_are_kept_and_ends_trimmed():
    c = CampaignInput(title="  Titre  ", body="  Ligne 1\nLigne 2  ", target=T)
    assert c.title == "Titre" and c.body == "Ligne 1\nLigne 2"


def test_audience_counts_deliveries_people_and_schools():
    rows = [{"user_id": "u1", "school_id": "s1"}, {"user_id": "u1", "school_id": "s2"}, {"user_id": "u2", "school_id": "s1"}, {"user_id": "p1", "school_id": None}]
    assert _audience(rows) == {"deliveries": 4, "people": 3, "schools": 2}


def test_send_recomputes_the_audience_and_never_exceeds_the_confirmed_figure():
    create = fn("create_campaign")
    assert "recipients = _recipients(c, t)" in create and 'aud["deliveries"] > body.confirmed_recipients' in create
    assert "AUDIENCE_CHANGED" in create and "Aperçu obligatoire avant une diffusion" in create
    assert "INSERT INTO notifications" in create and "ON CONFLICT DO NOTHING" in create        # one per (campaign, account, space)
    assert "IdempotentExecutor" in ROUTER and "idem.execute(" in create                         # double click / lost response
    assert "PLATFORM_NOTIFICATION_CAMPAIGN_SENT" in create and "people_count" in create


def test_zero_recipient_is_blocked_and_preview_creates_nothing():
    assert 'NO_RECIPIENT = "Aucun destinataire ne correspond actuellement à cette cible."' in ROUTER
    prev = fn("preview_campaign")
    assert "actor.require(SEND_CAP)" in prev and "INSERT" not in prev


def test_internal_links_and_expiry():
    create = fn("create_campaign")
    assert "LINK_RE.match(body.link_path)" in create and 'startswith("//")' in create
    assert "body.expires_at <= datetime.now(timezone.utc)" in create
    assert "(expires_at IS NULL OR expires_at>now())" in fn("_inbox")                           # expired: gone from bells


def test_history_is_paginated_searchable_and_read_only():
    lst = fn("list_campaigns")
    assert "actor.require(SEND_CAP)" in lst and "(p.created_at, p.id) < (CAST(:ca AS timestamptz), CAST(:cid AS uuid))" in lst
    assert "ORDER BY p.created_at DESC, p.id DESC" in lst and "Curseur de pagination invalide" in lst
    assert "edusync_search_key(p.title)" in ROUTER and "'EXPIRED'" in ROUTER
    for verb in ("put", "patch", "delete"):
        assert f'@router.{verb}("/platform/notification-campaigns' not in ROUTER                 # immutable once sent
    detail = fn("campaign_detail")
    assert "actor.require(SEND_CAP)" in detail and "audit_event_id" in detail and "LIMIT 50" in detail
    mig = (ROOT / "backend/migrations/0081_notification_campaigns_history.sql").read_text(encoding="utf-8")
    assert "people_count" in mig and "gin_trgm_ops" in mig
    assert "0081_notification_campaigns_history.sql" in (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


def test_frontend_composer_and_history():
    for x in ("Notification interne à l’application", "aucun SMS, WhatsApp ni e-mail", "Destinataires", "Contenu", "Options", "Aperçu",
              "Aperçu dans la cloche du destinataire", "Confirmer l’envoi", "Vous êtes sur le point d’envoyer", "Dupliquer",
              "Déterminée au moment de l’envoi", "Choisissez l’école, puis la personne", "Charger la suite", "Expirée"):
        assert x in UI or x in API, x
    assert "Rechercher</button>" not in UI and "window.setTimeout(() => set({q: qInput}), 300)" in UI
    assert "previewAudience(" in UI and "confirmed_recipients" in UI and "useRef(crypto.randomUUID())" in UI
    assert "AudienceChangedError" in UI and "BellItem" in UI                                     # real bell component as preview
    assert "fetchSchools(" in UI and "fetchIdentities(" in UI and "fetchMembers(" in UI            # server-side selectors
    assert "'INFO'" in API and "'WARNING'" in API and "'CRITICAL'" in API and "URGENT" not in API
