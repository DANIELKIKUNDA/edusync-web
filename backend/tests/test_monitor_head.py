"""Owner, 2026-11-21: UptimeRobot (free) probes with HEAD and saw 405 → « down » while the site was up."""
from fastapi.testclient import TestClient

from edusync.bootstrap.app import create_app


def _client():
    return TestClient(create_app(), raise_server_exceptions=False)


def test_head_on_health_answers_like_get_without_body():
    with _client() as c:
        get, head = c.get("/health"), c.head("/health")
    assert get.status_code == 200 and head.status_code == 200
    assert head.content == b"" and head.headers.get("content-type", "").startswith("application/json")


def test_head_stays_refused_outside_the_monitoring_addresses():
    """A GET route with effects (exports archive the document) must never be triggered by a probe."""
    with _client() as c:
        r = c.head("/api/v1/schooling/exports/families.xlsx")
    assert r.status_code in (401, 403, 405)          # never executed as a GET by the middleware


def test_middleware_is_innermost_and_limited():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "src/edusync/bootstrap/app.py").read_text(encoding="utf-8")
    assert src.index("app.add_middleware(MonitorHeadMiddleware)") < src.index("app.add_middleware(LiveChangesMiddleware")
    from edusync.shared.infrastructure.monitor_head import MONITOR_HEAD_PATHS
    assert MONITOR_HEAD_PATHS == frozenset({"/health", "/api/v1/setup/status"})
