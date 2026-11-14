"""État du service (lot 2026-10): contracts. Degradations (slow database, Redis down, stale / missing worker heartbeat,
outbox backlog and drain, storage down / absent, backup ok / late / failed / future / unreadable), shared measurement
under 20 concurrent requests, RBAC and absence of secrets are proven by tools/local/health_probe.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/platform_health/api/router.py").read_text(encoding="utf-8")
UI = (ROOT / "frontend/src/platform/health.tsx").read_text(encoding="utf-8")


def test_existing_state_model_is_preserved():
    assert 'RANK = {"OK": 0, "NOT_CONFIGURED": 1, "DEGRADED": 2, "DOWN": 3}' in ROUTER
    assert 'configured = [c for c in components if c["state"] != "NOT_CONFIGURED"]' in ROUTER   # not configured ≠ healthy
    for label in ("Opérationnel", "Dégradé", "Hors service", "Non configuré"):
        assert label in UI


def test_measurement_is_shared_and_fresh():
    assert "MEASURE_TTL = 5.0" in ROUTER and "with _lock:" in ROUTER and '"shared": True' in ROUTER
    assert 'c.setdefault("measured_at", checked)' in ROUTER and '"depends_on"' in ROUTER and '"summary"' in ROUTER
    assert 'actor.require("platform.health.read")' in ROUTER


def test_queues_backup_and_provider_without_secrets():
    assert '"oldest_seconds": queue.get("outbox_oldest_s")' in ROUTER and '"failed": queue["sms_dead"]' in ROUTER
    assert 'comp["provider"] = {"state": sms["state"]}' in ROUTER
    assert '"restore_verified": bool(info.get("restore_verified"))' in ROUTER and "late = ok and age >= 26 * 3600" in ROUTER
    assert 'raise ValueError("date future")' in ROUTER
    for leak in ("redis_url\"]", "database_url", "password", "token\""):
        assert leak not in ROUTER.split("def measure(", 1)[1].split("return {", 1)[1]


def test_frontend_freshness_cooldown_stale_protection_and_order():
    for x in ("Tous les services fonctionnent normalement", "Certains services sont dégradés", "Incident en cours", "Donnée périmée",
              "Mesure en cours…", "Mesurer maintenant", "Actualisation automatique", "document.visibilityState === 'visible'",
              "if (id !== reqId.current) return;", "COOLDOWN_MS", "Dépendances", "File d’attente", "restauration",
              "Historique conservé : 26 h par minute, 7 jours par heure", "Erreurs regroupées", "Signaux clés", "Incident en cours",
              "ne dégrade pas l’état actuel", "Journal d’audit</dt><dd>Non disponible"):
        assert x in UI, x
    # phone priority (after the incident list): server, database, workers, backup, storage, messaging, errors, cache
    assert "const ORDER = ['api', 'host', 'database', 'worker_outbox', 'worker_communications', 'backup', 'storage', 'messaging', 'errors', 'redis'];" in UI
    assert "Traceback" not in UI and "stack" not in UI.lower()
