"""Supervision de production (owner, 2026-11-14): host resources, external heartbeat, backup heartbeat, compose and docs."""
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from edusync.modules.platform_health.application import heartbeat as hb
from edusync.modules.platform_health.application.host import host_component

ROOT = Path(__file__).resolve().parents[2]


def settings(**k):
    base = dict(host_disk_path="/", host_memory_warn_percent=85, host_memory_critical_percent=95, host_disk_warn_percent=80,
                host_disk_critical_percent=90, host_load_warn_per_cpu=1.5, host_load_critical_per_cpu=3.0,
                heartbeat_url="https://hc-ping.example/abc", heartbeat_interval_seconds=60, platform_alert_delay_seconds=300)
    return SimpleNamespace(**{**base, **k})


def fake_proc(tmp_path, total_kb, available_kb, load5):
    (tmp_path / "meminfo").write_text(f"MemTotal: {total_kb} kB\nMemFree: 1 kB\nMemAvailable: {available_kb} kB\n", encoding="ascii")
    (tmp_path / "loadavg").write_text(f"0.10 {load5} 0.30 1/200 999\n", encoding="ascii")
    return str(tmp_path)


@pytest.fixture
def disk(monkeypatch):
    def set_used(percent):
        monkeypatch.setattr(os, "statvfs", raising=False, value=lambda p: SimpleNamespace(f_blocks=1000, f_frsize=40 * 1024 ** 2, f_bavail=int(1000 * (100 - percent) / 100)))
    set_used(40)
    return set_used


def test_host_ok_then_warning_then_critical(tmp_path, disk):
    s = settings()
    ok = host_component(s, proc=fake_proc(tmp_path, 4_000_000, 2_000_000, 0.5), cpus=2)
    assert ok["state"] == "OK" and ok["key"] == "host" and "Mémoire 50 %" in ok["detail"] and "Disque 40 %" in ok["detail"]
    assert ok["host"]["memory_total_mb"] == 3906 and ok["host"]["cpus"] == 2
    warn = host_component(s, proc=fake_proc(tmp_path, 4_000_000, 400_000, 0.5), cpus=2)
    assert warn["state"] == "DEGRADED" and "mémoire utilisée à 90 %" in warn["detail"]
    disk(92)
    crit = host_component(s, proc=fake_proc(tmp_path, 4_000_000, 2_000_000, 7.0), cpus=2)
    assert crit["state"] == "DOWN" and "disque rempli à 92 %" in crit["detail"] and "processeur saturé" in crit["detail"]


def test_host_not_configured_without_proc(tmp_path):
    out = host_component(settings(), proc=str(tmp_path / "absent"))
    assert out["state"] == "NOT_CONFIGURED" and "indisponible" in out["detail"]


@pytest.fixture(autouse=True)
def reset_heartbeat():
    hb._down_since.clear(); hb._last_sent["at"] = float("-inf"); hb._warned["bad_url"] = False


def body(*down):
    return {"components": [{"key": "api", "label": "API", "state": "OK", "detail": ""}] +
                          [{"key": k, "label": k.title(), "state": "DOWN", "detail": f"{k} injoignable"} for k in down]}


def test_heartbeat_ok_throttled_then_fail_after_the_alert_delay_and_back():
    sent = []
    send = lambda url, data: sent.append((url, data))
    s = settings()
    assert hb.beat(s, body(), now=1000, send=send) == "ok" and sent[-1] == ("https://hc-ping.example/abc", None)
    assert hb.beat(s, body(), now=1030, send=send) == "throttled"
    assert hb.beat(s, body("database"), now=1100, send=send) == "ok"          # down for 0 s: not yet an incident
    assert hb.beat(s, body("database"), now=1130, send=send) == "throttled"   # 30 s after the last ping, still < delay
    assert hb.beat(s, body("database"), now=1400, send=send) == "fail"
    url, data = sent[-1]
    assert url == "https://hc-ping.example/abc/fail" and "Database : database injoignable" in data.decode()
    assert hb.beat(s, body(), now=1410, send=send) == "throttled"            # recovered; next ok within the interval
    assert hb.beat(s, body(), now=1500, send=send) == "ok"


def test_heartbeat_reports_an_impossible_measure_and_never_raises():
    s = settings()
    calls = []
    assert hb.beat(s, None, now=0, send=lambda u, d: calls.append(u)) == "ok"       # first sight: the delay starts
    assert hb.beat(s, None, now=400, send=lambda u, d: calls.append(u)) == "fail" and calls[-1].endswith("/fail")

    def boom(url, data):
        raise OSError("réseau")
    assert hb.beat(s, body(), now=10_000, send=boom) == "error"


def test_heartbeat_disabled_or_refused_without_https(caplog):
    assert hb.beat(settings(heartbeat_url=""), body(), now=1, send=None) == "disabled"
    assert hb.beat(settings(heartbeat_url="http://hc-ping.example/abc"), body(), now=1, send=None) == "disabled"
    assert "hc-ping.example" not in caplog.text                                   # the secret URL is never logged


def test_health_screen_and_loop_wiring():
    router = (ROOT / "backend/src/edusync/modules/platform_health/api/router.py").read_text(encoding="utf-8")
    alerts = (ROOT / "backend/src/edusync/modules/platform_health/application/alerts.py").read_text(encoding="utf-8")
    screen = (ROOT / "frontend/src/platform/health.tsx").read_text(encoding="utf-8")
    assert "components.append(host_component(services.settings))" in router
    assert "beat(services.settings, body)" in alerts and alerts.index("evaluate(services, body=body)") < alerts.index("beat(services.settings, body)")
    assert "host: 'pulse'" in screen and "'api', 'host'" in screen


def test_backup_heartbeat_and_compose():
    script = (ROOT / "deploy/backup/backup.sh").read_text(encoding="utf-8")
    assert 'heartbeat /start' in script and 'heartbeat "" "sauvegarde vérifiée"' in script and "heartbeat /fail" in script
    assert "https://*" in script and 'echo "$HEARTBEAT"' not in script
    assert "curl" in (ROOT / "deploy/backup/Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8")
    assert "EDUSYNC_HEARTBEAT_URL: ${EDUSYNC_HEARTBEAT_URL:-}" in compose
    assert "BACKUP_HEARTBEAT_URL: ${EDUSYNC_BACKUP_HEARTBEAT_URL:-}" in compose


def test_runbook_covers_every_layer():
    doc = (ROOT / "deploy/coolify/README.md").read_text(encoding="utf-8")
    for part in ("## 9. Supervision", "Sentinel", "Server Disk Usage", "Container Status Changes", "Healthchecks.io",
                 "EDUSYNC_HEARTBEAT_URL", "EDUSYNC_BACKUP_HEARTBEAT_URL", "Ressources du serveur", "SMTP",
                 "Avant l’ouverture de la première école"):
        assert part in doc, part
