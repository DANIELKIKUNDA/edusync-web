"""Live changes (owner, 2026-11-01): « quand un caissier encaisse, après la validation, automatiquement tout le monde voit
sans recharger » — every school role. The signal names only domains; the screens re-read with their own rights."""
from __future__ import annotations

import json
from pathlib import Path

from edusync.shared.infrastructure import realtime
from edusync.shared.infrastructure.realtime import live_domains

ROOT = Path(__file__).resolve().parents[2]


def test_every_school_write_reaches_the_screens_that_show_it():
    assert live_domains("POST", "/api/v1/finance/checkout/collect") == ("finance",)
    assert live_domains("POST", "/api/v1/finance/cash/expenses") == ("finance",)
    assert set(live_domains("POST", "/api/v1/schooling/enrollments/family")) == {"students", "headcounts", "finance"}
    assert live_domains("PATCH", "/api/v1/schooling/students/x") == ("students", "headcounts")
    assert live_domains("POST", "/api/v1/stewardship/stock/movements") == ("stock",)
    assert live_domains("POST", "/api/v1/personnel") == ("personnel",)
    assert live_domains("POST", "/api/v1/effectifs/deposits") == ("headcounts",)


def test_reads_previews_prints_and_sign_in_never_signal():
    for method, path in [("GET", "/api/v1/finance/cash/current"), ("POST", "/api/v1/communications/templates/preview"),
                         ("POST", "/api/v1/import/students/analyze"), ("POST", "/api/v1/finance/reports/periodic/pdf"),
                         ("POST", "/api/v1/auth/login"), ("POST", "/api/v1/platform/schools")]:
        assert live_domains(method, path) == (), (method, path)


def test_the_signal_carries_domains_only(monkeypatch):
    sent = []
    class FakeRedis:
        @classmethod
        def from_url(cls, *a, **k): return cls()
        def publish(self, channel, msg): sent.append((channel, msg))
    import sys, types
    monkeypatch.setitem(sys.modules, "redis", types.SimpleNamespace(Redis=FakeRedis))
    assert realtime.publish_school_changed("redis://x", "school-1", ("finance",))
    channel, msg = sent[0]
    assert channel == "edusync:rt:school:school-1"
    assert set(json.loads(msg)) == {"type", "domains", "at"} and json.loads(msg)["domains"] == ["finance"]


def test_wired_once_for_the_whole_api_and_open_to_every_member():
    app = (ROOT / "backend/src/edusync/bootstrap/app.py").read_text(encoding="utf-8")
    deps = (ROOT / "backend/src/edusync/bootstrap/dependencies.py").read_text(encoding="utf-8")
    nc = (ROOT / "backend/src/edusync/modules/notifications_center/api/router.py").read_text(encoding="utf-8")
    assert "app.add_middleware(LiveChangesMiddleware, redis_url=cfg.redis_url)" in app
    assert "request.state.live_school_id = school_id" in deps
    stream = nc.split('@router.get("/live/stream")', 1)[1].split("@router.get(", 1)[0]
    assert "require_school_actor" in stream and "_need(" not in stream     # signals carry no data: any member listens
