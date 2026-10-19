"""Diagnosable « État du service » (lot 2026-10): pure parts of signals.py and contracts. Grouping, current vs
historical health, recovery, golden signals, redaction and RBAC against the real application are proven by
tools/local/observability_probe.py."""
from pathlib import Path

from edusync.shared.infrastructure import signals

ROOT = Path(__file__).resolve().parents[2]
MW = (ROOT / "backend/src/edusync/shared/infrastructure/observability.py").read_text(encoding="utf-8")
HEALTH = (ROOT / "backend/src/edusync/modules/platform_health/api/router.py").read_text(encoding="utf-8")


def test_redaction_removes_values_identifiers_and_secrets():
    msg = ("échec password=hunter2 token: abc.def pour jean.dupont@example.test id 0b7c3f0e-1111-4c2a-9e55-0123456789ab "
           "montant 4815162342 'valeur' https://user:pw@db.internal:5432/x C:\\srv\\app\\secret.txt Bearer eyJhbGciOi\nligne 2")
    out = signals.redact(msg)
    for leak in ("hunter2", "abc.def", "jean.dupont", "0b7c3f0e", "4815162342", "valeur", "db.internal", "secret.txt", "eyJhbGciOi", "ligne 2"):
        assert leak not in out, leak
    assert out.startswith("échec password=<masqué>") and len(out) <= 160
    assert signals.redact("(psycopg.errors.QueryCanceled) timeout\n[SQL: SELECT * FROM users WHERE email='a@b.c']") == "(psycopg.errors.QueryCanceled) timeout"
    assert signals.redact("") == ""


def test_group_identity_is_route_template_status_and_type():
    a = signals.group_id("GET", "/api/v1/platform/schools/{school_id}", 500, "RuntimeError")
    assert a == signals.group_id("GET", "/api/v1/platform/schools/{school_id}", 500, "RuntimeError") and len(a) == 12
    assert a != signals.group_id("GET", "/api/v1/platform/schools/{school_id}", 503, "RuntimeError")
    assert a != signals.group_id("POST", "/api/v1/platform/schools/{school_id}", 500, "RuntimeError")


def test_percentile_is_the_bucket_edge_never_a_fake_precise_figure():
    agg = {"req": 100, "e5": 0, "e4": 0, "ls": 0, **{f"b{i}": 0 for i in range(7)}}
    agg.update(b0=50, b1=45, b3=5)
    assert signals._percentile(agg, .5) == 50 and signals._percentile(agg, .95) == 100 and signals._percentile(agg, .99) == 500
    agg.update(b3=0, b6=5)
    assert signals._percentile(agg, .99) is None and signals._signals(agg, 5)["latency_p95_over"] is False
    assert signals._signals({**agg, "b0": 0, "b1": 0, "b6": 100}, 5)["latency_p95_over"] is True
    assert signals._signals({k: 0 for k in agg}, 5)["latency_p95_ms"] is None


def test_current_state_comes_from_active_errors_only():
    day = {"server_errors": 7}
    old = [{"active": False, "count_1h": 0}]
    assert signals.errors_state(old, {}, day)["state"] == "OK"                       # history never degrades
    assert "historique" in signals.errors_state(old, {}, day)["explain"]
    cur = signals.errors_state([{"active": True, "count_1h": 3}, *old], {}, day)
    assert cur["state"] == "DEGRADED" and cur["active_groups"] == 1 and "en cours" in cur["explain"]   # always explainable
    assert signals.errors_state([], {}, {"server_errors": 0})["explain"] == "Aucune erreur inattendue sur 24 h"
    assert signals.ACTIVE_WINDOW_S == 300


def test_middleware_records_route_template_off_the_request_path_and_answers_with_a_reference():
    assert "route=request.scope.get('route')" in MW and "run_in_executor(None" in MW
    assert "if not request.url.path.startswith('/api/'):" in MW
    assert "'X-Correlation-ID':correlation_id" in MW and "Référence : {correlation_id[:8]}" in MW
    assert "status >= 500" in (ROOT / "backend/src/edusync/shared/infrastructure/signals.py").read_text(encoding="utf-8")


def test_health_exposes_diagnostics_with_rbac():
    for route in ('@router.get("/health/errors")', '@router.get("/health/errors/{group_id}")', '@router.get("/health/history")'):
        assert route in HEALTH
    assert HEALTH.count('actor.require("platform.health.read")') == 5     # health, errors, error detail, history, incidents
    assert '"alert_delivery": "EMAIL"' in HEALTH and 'g["audit_link"] = "NOT_AVAILABLE"' in HEALTH
    assert '"SIMULATED": "Simulé (jamais certifié)"' in HEALTH and '"certified": False if st != "CONFIGURED" else None' in HEALTH
