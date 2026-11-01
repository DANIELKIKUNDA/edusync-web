"""« Niveau plateforme terminé » (lot 2026-10): alerts, external probe, E2E staging, production procedure, security
scan, retention, backup timing, API processes. Real behaviour proven by tools/local/alerts_probe.py (21 checks),
tools/ci/e2e_staging.py (run locally and after each staging deploy), tools/local/load_test.py and the documents."""
from pathlib import Path

from edusync.modules.communications.domain.email_templates import render

ROOT = Path(__file__).resolve().parents[2]
WF = ROOT / ".github/workflows"
ALERTS = (ROOT / "backend/src/edusync/modules/platform_health/application/alerts.py").read_text(encoding="utf-8")
HEALTH = (ROOT / "backend/src/edusync/modules/platform_health/api/router.py").read_text(encoding="utf-8")
PROVISION = (ROOT / "backend/scripts/provision_database.py").read_text(encoding="utf-8")


def test_alerts_once_after_delay_to_managers_and_extra_recipients():
    assert "r.code='MANAGER_SYSTEME'" in ALERTS and "platform_alert_recipients WHERE active" in ALERTS
    assert "pg_try_advisory_xact_lock" in ALERTS and 'inc["notified_at"] is None' in ALERTS
    assert "cfg.platform_alert_delay_seconds" in ALERTS and 'idempotency_key=f"platform-incident:{incident[\'id\']}:{kind}"' in ALERTS
    assert '("0083_platform_alerts", "0083_platform_alerts.sql")' in PROVISION
    sql = (ROOT / "backend/migrations/0083_platform_alerts.sql").read_text(encoding="utf-8")
    assert "platform_incidents_one_open" in sql and "FORCE ROW LEVEL SECURITY" in sql


def test_alert_email_template_escapes_and_names_the_platform():
    c = render("PLATFORM_ALERT", recipient_name="<b>X</b>", school_name=None, subject="[EduSync] Incident : API hors service",
               body="Le service « API » est hors service.\nRaison : <script>", link=None)
    assert c.subject.startswith("[EduSync] Incident") and "<script>" not in c.html and "&lt;b&gt;X&lt;/b&gt;" in c.html
    assert "Plateforme EduSync (alerte automatique)" in c.text


def test_recipient_management_is_manager_only_with_step_up_and_audited():
    assert HEALTH.count('actor.require("platform.collaborators.manage")') == 3
    assert HEALTH.count('require_recent_mfa(services, actor, "platform.collaborators.manage")') == 2
    for a in ("PLATFORM_ALERT_RECIPIENT_ADDED", "PLATFORM_ALERT_RECIPIENT_REMOVED", "PLATFORM_ALERT_TEST_SENT"):
        assert a in HEALTH
    assert '"email": r["email"] if can_manage else _mask(r["email"])' in HEALTH


def test_external_probe_e2e_production_and_scan_workflows():
    up = (WF / "uptime.yml").read_text(encoding="utf-8")
    # 2026-10-31 (owner): manual run only — the 30-minute schedule used ~1 440 of the 2 000 free monthly minutes and blocked
    # the CI; the application itself e-mails an incident after 5 minutes of outage.
    assert "schedule:" not in up and "workflow_dispatch:" in up
    assert "/api/v1/setup/status" in up and "gh issue create" in up and "gh issue close" in up
    e2e = (WF / "e2e-staging.yml").read_text(encoding="utf-8")
    assert "workflows: [Deploy staging]" in e2e and "secrets.E2E_PLATFORM_TOTP_SECRET" in e2e
    prod = (WF / "deploy-production.yml").read_text(encoding="utf-8")
    triggers = prod.split("\non:", 1)[1].split("\npermissions:", 1)[0]
    assert "workflow_dispatch" in triggers and "workflow_run" not in triggers and "schedule" not in triggers and "push" not in triggers
    assert 'PRODUCTION ${SHA:0:8}' in prod and "environment: production" in prod
    for wf in ("ci.yml", "deploy-staging.yml", "e2e-staging.yml"):
        assert wf in prod
    zap = (WF / "security-scan.yml").read_text(encoding="utf-8")
    assert "zap-baseline.py" in zap and "zap-full-scan" not in zap


def test_e2e_script_is_read_only_and_never_prints_secrets():
    s = (ROOT / "tools/ci/e2e_staging.py").read_text(encoding="utf-8")
    assert "print(PASSWORD" not in s and "print(SECRET" not in s
    for verb in ('call("PUT"', 'call("DELETE"', 'call("PATCH"'):
        assert verb not in s
    posts = [line for line in s.splitlines() if 'call("POST"' in line]
    assert all(any(p in line for p in ("/auth/login", "/auth/mfa/verify", "/auth/switch", "/auth/refresh", "/auth/logout")) for line in posts)


def test_retention_is_off_by_default_and_never_purges_audit():
    s = (ROOT / "backend/scripts/retention_purge.py").read_text(encoding="utf-8")
    assert 'ap.add_argument("--apply", action="store_true"' in s and "if apply and n else 0" in s
    assert "DELETE FROM audit_events" not in s and "BUSINESS_DECISION_REQUIRED" in s


def test_backup_restore_is_timed_and_api_runs_several_processes():
    b = (ROOT / "deploy/backup/backup.sh").read_text(encoding="utf-8")
    assert "RESTORE_SECONDS=$(( $(date +%s) - restore_start ))" in b and '"restore_seconds":%s' in b
    assert '"restore_seconds": info.get("restore_seconds")' in HEALTH
    assert "ENV WEB_CONCURRENCY=2" in (ROOT / "backend/Dockerfile").read_text(encoding="utf-8")
