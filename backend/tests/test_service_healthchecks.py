"""Owner, 2026-11-21: Coolify showed « Running (no healthcheck) » — workers and backup now report their health."""
import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("worker_health", ROOT / "backend/scripts/worker_health.py")
worker_health = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker_health)


def test_worker_heartbeat_age_rule_matches_the_health_screen():
    now = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)
    assert worker_health.age_seconds((now - timedelta(seconds=30)).isoformat(), now) == 30
    assert worker_health.age_seconds(None, now) is None and worker_health.age_seconds("pas une date", now) is None
    assert worker_health.MAX_AGE_SECONDS == 300
    assert worker_health.main(["x", "inconnu"]) == 2


def test_compose_declares_the_healthchecks_with_a_start_period():
    services = yaml.safe_load((ROOT / "docker-compose.coolify.yml").read_text(encoding="utf-8"))["services"]
    for name, worker in (("outbox-worker", "outbox"), ("communications-worker", "communications")):
        hc = services[name]["healthcheck"]
        assert hc["test"] == ["CMD", "python", "scripts/worker_health.py", worker] and hc["start_period"] == "60s"
    hc = services["backup"]["healthcheck"]
    assert hc["test"] == ["CMD", "/bin/sh", "/usr/local/bin/edusync-backup-health"] and hc["start_period"] == "30m"


def test_backup_health_script_ships_in_the_image_and_reads_the_status_only():
    assert "COPY backup-health.sh /usr/local/bin/edusync-backup-health" in (ROOT / "deploy/backup/Dockerfile").read_text(encoding="utf-8")
    sh = (ROOT / "deploy/backup/backup-health.sh").read_text(encoding="utf-8")
    assert '"ok":true' in sh and "-mmin -1800" in sh and "rm " not in sh
