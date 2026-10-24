"""School maintenance from the settings (settings parity pass 3, 2026-10-24) — Desktop golden master references:
app/ui/settings_page.py (_backup_now, _test_backup, _export_diagnostic), app/services/diagnostics.py.

The Web database is shared and backed up daily by the platform (deploy/backup, status shown in the platform health).
A school therefore never copies a database file: « Sauvegarder maintenant » exports a verified archive of ITS OWN data
(tenant transaction, row level security AND an explicit school filter), and « Tester » rebuilds that archive in memory and
re-checks every SHA-256 and every row count, like the Desktop backup test. Restoring stays a platform operation.

The diagnostic copies app/services/diagnostics.py: versions and volumes only — no pupil name, phone number or amount.
"""
from __future__ import annotations

import hashlib
import io
import json
import zipfile
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import text

from edusync import __version__

# The school's business data, in restore order. Technical / security tables (users, tokens, MFA, idempotency, outbox,
# audit) are never exported by a school.
SCHOOL_DATA_TABLES: tuple[str, ...] = (
    "academic_years", "school_sections", "school_options", "school_classes",
    "fee_categories", "fee_types", "tariffs", "fee_schedules", "school_billing_policy", "school_payment_policy",
    "school_benefit_policies", "school_admission_conditions", "school_policy_documents", "school_print_settings",
    "school_products", "contribution_types",
    "families", "guardians", "family_guardians", "students", "enrollments", "class_assignments", "student_benefits",
    "student_status_events",
    "staff_functions", "staff_members", "staff_assignments", "staff_student_links",
    "finance_charges", "finance_payments", "finance_payment_allocations", "finance_payment_reversals", "finance_receipt_prints",
    "finance_decisions", "finance_decision_applications", "finance_advance_funds", "finance_credits",
    "finance_cash_sessions", "finance_cash_events", "finance_cash_expenses", "finance_product_sales", "material_contributions",
    "inventory_items", "inventory_assets",
)
IDENTITY_COLUMNS = "id,code,name,email,phone,address,city,province,motto,created_at,updated_at,version"
DIAGNOSTIC_VOLUMES: tuple[tuple[str, str], ...] = (
    ("students", "Élèves"), ("enrollments", "Inscriptions"), ("school_classes", "Classes"), ("families", "Familles"),
    ("staff_members", "Personnel"), ("finance_charges", "Frais dus"), ("finance_payments", "Paiements"),
    ("devices", "Appareils synchronisés"), ("sync_conflicts", "Conflits de synchronisation"), ("audit_events", "Événements d’audit"),
)


def _json_default(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (Decimal, UUID)):
        return str(v)
    if isinstance(v, (bytes, memoryview)):
        return None                       # binary columns are never exported (logos live in the object store)
    return str(v)


def _rows(conn, table: str, school_id: UUID) -> list[dict[str, Any]] | None:
    """Rows of one table for this school, or None when the table is absent or not readable (savepoint: the export goes on)."""
    sp = conn.begin_nested()
    try:
        rows = [dict(r) for r in conn.execute(text(f'SELECT * FROM "{table}" WHERE school_id = :sid'), {"sid": str(school_id)}).mappings().all()]
        sp.commit()
        return rows
    except Exception:  # noqa: BLE001 — absent table / column / privilege: reported in the manifest
        sp.rollback()
        return None


def export_school_data(conn, school_id: UUID, *, generated_by: str | None = None) -> tuple[bytes, dict[str, Any]]:
    """A ZIP: manifest.json (counts + SHA-256 of every file) and one JSON file per table."""
    school = conn.execute(text(f"SELECT {IDENTITY_COLUMNS} FROM schools WHERE id = :sid"), {"sid": str(school_id)}).mappings().first()
    if school is None:
        raise LookupError("École introuvable")
    files: dict[str, bytes] = {"data/school.json": json.dumps(dict(school), default=_json_default, ensure_ascii=False, indent=1).encode("utf-8")}
    tables: list[dict[str, Any]] = [{"table": "schools", "file": "data/school.json", "rows": 1}]
    skipped: list[str] = []
    for table in SCHOOL_DATA_TABLES:
        rows = _rows(conn, table, school_id)
        if rows is None:
            skipped.append(table)
            continue
        name = f"data/{table}.json"
        files[name] = json.dumps(rows, default=_json_default, ensure_ascii=False, indent=1).encode("utf-8")
        tables.append({"table": table, "file": name, "rows": len(rows)})
    for t in tables:
        t["sha256"] = hashlib.sha256(files[t["file"]]).hexdigest()
    manifest = {
        "format": "edusync-school-export", "format_version": 1, "app_version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "generated_by": generated_by,
        "school": {"id": str(school_id), "code": school["code"], "name": school["name"]},
        "tables": tables, "skipped_tables": skipped, "total_rows": sum(t["rows"] for t in tables),
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=1))
        for name, data in files.items():
            z.writestr(name, data)
        z.writestr("LISEZMOI.txt", "Copie des données de l’école générée par EduSync.\n"
                   "Chaque fichier est contrôlé par son empreinte SHA-256 (manifest.json).\n"
                   "Document confidentiel : il contient des données personnelles d’élèves et de familles.\n"
                   "La restauration d’une école se fait uniquement par l’équipe de la plateforme EduSync.\n")
    return buf.getvalue(), manifest


def verify_export(data: bytes) -> dict[str, Any]:
    """Desktop _test_backup: reopen the archive, recompute every SHA-256, re-read every JSON file and its row count."""
    problems: list[str] = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        bad = z.testzip()
        if bad:
            problems.append(f"Fichier endommagé dans l’archive : {bad}")
        manifest = json.loads(z.read("manifest.json"))
        for t in manifest["tables"]:
            raw = z.read(t["file"])
            if hashlib.sha256(raw).hexdigest() != t["sha256"]:
                problems.append(f"Empreinte différente : {t['table']}")
            parsed = json.loads(raw)
            count = 1 if t["table"] == "schools" else len(parsed)
            if count != t["rows"]:
                problems.append(f"Nombre de lignes différent : {t['table']}")
    return {"ok": not problems, "problems": problems, "tables": len(manifest["tables"]), "total_rows": manifest["total_rows"],
            "skipped_tables": manifest["skipped_tables"], "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def numbering(conn, school_id: UUID) -> dict[str, str]:
    """Next codes, read without consuming them (Desktop « numérotation automatique »). Formats: schooling next_code
    (ELV-00001 / FAM-00001) and finance next_receipt_number (PREFIX-YEAR-000001)."""
    counters = {r["namespace"]: int(r["current_value"]) for r in conn.execute(text(
        "SELECT namespace,current_value FROM school_sequence_counters WHERE school_id=:sid"), {"sid": str(school_id)}).mappings()}
    year = date.today().year
    receipts = conn.execute(text("SELECT last_number FROM finance_receipt_sequences WHERE school_id=:sid AND year=:y"),
                            {"sid": str(school_id), "y": year}).scalar_one_or_none() or 0
    prefix = conn.execute(text("SELECT receipt_prefix FROM school_print_settings WHERE school_id=:sid"), {"sid": str(school_id)}).scalar_one_or_none() or "REC"
    return {"student": f"ELV-{counters.get('STUDENT', 0) + 1:05d}", "family": f"FAM-{counters.get('FAMILY', 0) + 1:05d}",
            "receipt": f"{prefix.strip().upper()}-{year}-{int(receipts) + 1:06d}"}


def _count(conn, table: str, school_id: UUID) -> int | None:
    sp = conn.begin_nested()
    try:
        n = int(conn.execute(text(f'SELECT count(*) FROM "{table}" WHERE school_id=:sid'), {"sid": str(school_id)}).scalar_one())
        sp.commit()
        return n
    except Exception:  # noqa: BLE001
        sp.rollback()
        return None


def diagnostic(conn, school_id: UUID, *, readiness: dict[str, Any] | None = None, backup: dict[str, Any] | None = None) -> dict[str, Any]:
    sp = conn.begin_nested()
    try:
        schema = conn.execute(text("SELECT max(version) FROM schema_migrations")).scalar_one_or_none()
        sp.commit()
    except Exception:  # noqa: BLE001 — the tenant role may not read the migration table
        sp.rollback()
        schema = None
    year = conn.execute(text("SELECT label,status FROM academic_years WHERE school_id=:sid AND status IN ('ACTIVE','PREPARED') ORDER BY (status='ACTIVE') DESC, start_date DESC LIMIT 1"),
                        {"sid": str(school_id)}).mappings().first()
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "app_version": __version__, "schema_version": schema,
        "database": conn.execute(text("SHOW server_version")).scalar_one(),
        "school_code": conn.execute(text("SELECT code FROM schools WHERE id=:sid"), {"sid": str(school_id)}).scalar_one_or_none(),
        "academic_year": dict(year) if year else None,
        "volumes": [{"key": t, "label": label, "count": _count(conn, t, school_id)} for t, label in DIAGNOSTIC_VOLUMES],
        "readiness": readiness, "backup": backup,
    }


def diagnostic_text(d: dict[str, Any]) -> str:
    lines = ["EDUSYNC ÉCOLE — RAPPORT DIAGNOSTIC", "==================================",
             f"Généré UTC : {d['generated_at']}", f"Version application : {d['app_version']}",
             f"Version schéma : {d['schema_version'] or 'indisponible'}", f"PostgreSQL : {d['database']}",
             f"École (code) : {d['school_code'] or '—'}",
             f"Année : {d['academic_year']['label'] + ' (' + d['academic_year']['status'] + ')' if d['academic_year'] else 'aucune année en cours'}"]
    if d.get("readiness"):
        lines.append(f"Paramétrage : {d['readiness'].get('percent')} %")
        for item in d["readiness"].get("items", []):
            lines.append(f"  - {item['label']} : {item['state']}")
    if d.get("backup"):
        lines.append(f"Sauvegarde plateforme : {d['backup'].get('state')} — {d['backup'].get('detail')}")
    lines += ["", "VOLUMÉTRIE (aucune donnée nominative)", "--------------------------------------"]
    lines += [f"{v['label']} : {v['count'] if v['count'] is not None else 'indisponible'}" for v in d["volumes"]]
    lines += ["", "Ce rapport ne contient ni noms d’élèves, ni téléphones, ni montants détaillés."]
    return "\n".join(lines) + "\n"
