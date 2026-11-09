from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_vigie_schema_has_incident_and_human_response_lifecycles():
    sql = (ROOT / "migrations/0111_vigie_edusync_supervision.sql").read_text()
    assert "condition_status" in sql and "OPEN','RESOLVED" in sql
    assert "response_status" in sql and "ACKNOWLEDGED" in sql and "IN_PROGRESS" in sql
    assert "supervision_one_open_incident" in sql
    assert "required_capability" in sql and "scope_type" in sql and "scope_value" in sql


def test_vigie_routes_by_capability_not_role_name():
    src = (ROOT / "src/edusync/modules/alerts/application/supervision.py").read_text()
    alerts = (ROOT / "src/edusync/modules/alerts/application/school_alerts.py").read_text()
    assert "capability_alert" in src
    assert "rc.capability_code=:cap" in alerts
    assert "rbac_assignment_scopes" in alerts
    for role in ("PROMOTEUR", "GESTIONNAIRE", "CAISSIER", "PREFET_ETUDES"):
        assert role not in src


def test_vigie_first_rules_are_measured_and_actionable():
    src = (ROOT / "src/edusync/modules/alerts/application/supervision.py").read_text()
    assert "FINANCE_CLASS_INSOLVENCY" in src
    assert "CASH_SESSION_NOT_CLOSED" in src
    assert "ENROLLMENTS_WITHOUT_CHARGES" in src
    assert "/finance?view=recovery&class=" in src
    assert "au moins deux mensualités impayées" in src


def test_push_click_is_connected_to_school_navigation():
    main = (ROOT.parent / "frontend/src/main.tsx").read_text()
    app = (ROOT.parent / "frontend/src/App.tsx").read_text()
    sw = (ROOT.parent / "frontend/public/sw.js").read_text()
    assert "edusync-push-open" in sw and "edusync-push-open" in main
    assert "edusync:navigate" in main and "edusync:navigate" in app
