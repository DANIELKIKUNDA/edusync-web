"""Settings parity pass 3 (owner request 2026-10-24, « ajoute tout ce qui reste »):
- school motto and document signatory / logo choice, printed on every PDF through one helper;
- numbering preview without consuming a number;
- a verified copy of the school's own data (never users, tokens, MFA or audit), and its integrity test;
- a diagnostic without personal data;
- the backup / diagnostic capabilities owned by ADMIN_SYSTEME_ECOLE become ACTIVE; restore stays PLANNED.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

from edusync.modules.documents.application.identity import signatory_line
from edusync.modules.settings.application.school_maintenance import SCHOOL_DATA_TABLES, diagnostic_text, verify_export

ROOT = Path(__file__).resolve().parents[2]
MIG = (ROOT / "backend/migrations/0088_settings_documents_backups_diagnostics.sql").read_text(encoding="utf-8")
REG = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
CAPS = {c["code"]: c for c in REG["capabilities"]}
ROUTER = (ROOT / "backend/src/edusync/modules/settings/api/router.py").read_text(encoding="utf-8")


def test_migration_is_additive_and_scoped():
    assert "GRANT UPDATE (motto) ON schools TO edusync_tenant" in MIG
    assert "GRANT SELECT ON schema_migrations TO edusync_tenant" in MIG
    for col in ("signatory_name", "signatory_title", "show_school_logo"):
        assert f"ADD COLUMN IF NOT EXISTS {col}" in MIG
    assert "DROP" not in MIG and "DELETE" not in MIG


def test_capabilities_activated_exactly_as_the_owner_assigned_them():
    for code in ("settings.backups.create", "settings.backups.test", "settings.diagnostics.read", "settings.diagnostics.export"):
        assert CAPS[code]["lifecycle"] == "ACTIVE", code
        assert [r for r, v in REG["standard_roles"].items() if code in v["capabilities"]] == ["ADMIN_SYSTEME_ECOLE"], code
        assert f"'{code}'" in ROUTER
    assert CAPS["settings.backups.restore"]["lifecycle"] == "PLANNED"      # restoring a school is a platform operation


def test_school_copy_never_contains_security_tables():
    forbidden = {"users", "account_tokens", "user_mfa_factors", "user_mfa_recovery_codes", "mfa_challenges", "idempotency_registry",
                 "outbox_events", "audit_events", "user_device_sessions", "push_subscriptions", "school_memberships"}
    assert not forbidden & set(SCHOOL_DATA_TABLES)


def _archive(tamper: bool = False) -> bytes:
    rows = json.dumps([{"id": 1}, {"id": 2}]).encode()
    manifest = {"tables": [{"table": "students", "file": "data/students.json", "rows": 2, "sha256": hashlib.sha256(rows).hexdigest()}],
                "total_rows": 2, "skipped_tables": []}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("manifest.json", json.dumps(manifest))
        z.writestr("data/students.json", rows + (b" " if tamper else b""))
    return buf.getvalue()


def test_copy_test_detects_any_alteration():
    assert verify_export(_archive())["ok"] is True
    bad = verify_export(_archive(tamper=True))
    assert bad["ok"] is False and "Empreinte différente : students" in bad["problems"]


def test_diagnostic_text_has_no_personal_data_fields():
    d = {"generated_at": "2026-10-24T00:00:00+00:00", "app_version": "x", "schema_version": "0088", "database": "16", "school_code": "C",
         "academic_year": None, "readiness": None, "backup": None, "volumes": [{"key": "students", "label": "Élèves", "count": 3}]}
    text = diagnostic_text(d)
    assert "Élèves : 3" in text and "ni noms d’élèves" in text


def test_signatory_line():
    assert signatory_line({"signatory_name": " Jean Kabeya ", "signatory_title": "Préfet des études"}) == "Jean Kabeya — Préfet des études"
    assert signatory_line({}) == ""


def test_motto_is_kept_when_a_client_does_not_send_it():
    assert "'motto' in body.model_fields_set" in ROUTER
