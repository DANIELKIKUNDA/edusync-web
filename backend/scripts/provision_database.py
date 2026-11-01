from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from edusync.bootstrap.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS = ROOT / "migrations"
TENANT_ROLE = "edusync_tenant"
PLATFORM_ROLE = "edusync_platform"
WORKER_ROLE = "edusync_worker"


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _ensure_role(conn, role: str, password: str) -> None:
    exists = conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname=:role"), {"role": role}).first()
    pwd = _sql_literal(password)
    if exists is None:
        conn.exec_driver_sql(
            f"CREATE ROLE {role} LOGIN PASSWORD {pwd} NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS"
        )
    else:
        conn.exec_driver_sql(
            f"ALTER ROLE {role} WITH LOGIN PASSWORD {pwd} NOSUPERUSER NOCREATEDB NOCREATEROLE "
            "NOINHERIT NOREPLICATION NOBYPASSRLS"
        )


def _execute_sql_file(conn, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    # Migration files contain PostgreSQL format('%I', ...) expressions, not
    # DBAPI placeholders. Do not let psycopg parse an empty parameter mapping.
    conn.exec_driver_sql(sql, execution_options={"no_parameters": True})


def _migration_applied(conn, version: str) -> bool:
    return conn.execute(text("SELECT 1 FROM schema_migrations WHERE version=:v"), {"v": version}).first() is not None


def _record_migration(conn, version: str) -> None:
    conn.execute(text("INSERT INTO schema_migrations(version) VALUES (:v) ON CONFLICT DO NOTHING"), {"v": version})


def _table_exists(conn, table: str) -> bool:
    return conn.execute(text("SELECT to_regclass(:name)"), {"name": f"public.{table}"}).scalar_one() is not None


def main() -> None:
    settings = Settings()
    settings.assert_provisioning_safe()
    owner_url = make_url(settings.owner_database_url)
    tenant_url = make_url(settings.tenant_database_url)
    platform_url = make_url(settings.platform_database_url)
    if tenant_url.username != TENANT_ROLE or platform_url.username != PLATFORM_ROLE:
        raise RuntimeError("Les URL PostgreSQL doivent utiliser edusync_tenant et edusync_platform")
    if not tenant_url.password or not platform_url.password:
        raise RuntimeError("Mots de passe PostgreSQL tenant/platform obligatoires")

    engine = create_engine(owner_url, future=True, pool_pre_ping=True)
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            CREATE TABLE IF NOT EXISTS schema_migrations(
              version varchar(96) PRIMARY KEY,
              applied_at timestamptz NOT NULL DEFAULT now()
            )
        """)

        # Upgrade-safe baseline adoption for a WEB-0A/0B database created before the ledger existed.
        if not _migration_applied(conn, "0001_foundation"):
            if _table_exists(conn, "schools"):
                _record_migration(conn, "0001_foundation")
            else:
                _execute_sql_file(conn, MIGRATIONS / "0001_foundation.sql")
                _record_migration(conn, "0001_foundation")

        if not _migration_applied(conn, "0002_idempotency_concurrency"):
            if _table_exists(conn, "idempotency_registry"):
                _record_migration(conn, "0002_idempotency_concurrency")
            else:
                _execute_sql_file(conn, MIGRATIONS / "0002_idempotency_concurrency.sql")
                _record_migration(conn, "0002_idempotency_concurrency")

        _ensure_role(conn, TENANT_ROLE, tenant_url.password)
        _ensure_role(conn, PLATFORM_ROLE, platform_url.password)
        worker_url = make_url(settings.worker_database_url) if settings.worker_database_url else None
        if worker_url is not None:
            if worker_url.username != WORKER_ROLE or not worker_url.password:
                raise RuntimeError("EDUSYNC_WORKER_DATABASE_URL doit utiliser edusync_worker avec un mot de passe")
            _ensure_role(conn, WORKER_ROLE, worker_url.password)

        if not _migration_applied(conn, "0003_g1_live_security"):
            _execute_sql_file(conn, MIGRATIONS / "0003_g1_live_security.sql")
            _record_migration(conn, "0003_g1_live_security")

        if not _migration_applied(conn, "0004_offline_finance_safe_mode"):
            _execute_sql_file(conn, MIGRATIONS / "0004_offline_finance_safe_mode.sql")
            _record_migration(conn, "0004_offline_finance_safe_mode")

        if not _migration_applied(conn, "0005_offline_finance_multi_cashier"):
            _execute_sql_file(conn, MIGRATIONS / "0005_offline_finance_multi_cashier.sql")
            _record_migration(conn, "0005_offline_finance_multi_cashier")

        if not _migration_applied(conn, "0006_capability_rbac_engine"):
            _execute_sql_file(conn, MIGRATIONS / "0006_capability_rbac_engine.sql")
            _record_migration(conn, "0006_capability_rbac_engine")
        if not _migration_applied(conn, "0007_owner_decision_manager_systeme"):
            _execute_sql_file(conn, MIGRATIONS / "0007_owner_decision_manager_systeme.sql")
            _record_migration(conn, "0007_owner_decision_manager_systeme")
        if not _migration_applied(conn, "0008_owner_approved_school_roles"):
            _execute_sql_file(conn, MIGRATIONS / "0008_owner_approved_school_roles.sql")
            _record_migration(conn, "0008_owner_approved_school_roles")
        if not _migration_applied(conn, "0009_secondary_leadership_roles"):
            _execute_sql_file(conn, MIGRATIONS / "0009_secondary_leadership_roles.sql")
            _record_migration(conn, "0009_secondary_leadership_roles")
        if not _migration_applied(conn, "0010_settings_domain"):
            _execute_sql_file(conn, MIGRATIONS / "0010_settings_domain.sql")
            _record_migration(conn, "0010_settings_domain")
        if not _migration_applied(conn, "0011_migrate_legacy_school_admin_rbac"):
            _execute_sql_file(conn, MIGRATIONS / "0011_migrate_legacy_school_admin_rbac.sql")
            _record_migration(conn, "0011_migrate_legacy_school_admin_rbac")

        # Keep provisioning aligned with the complete application schema.  The previous
        # provisioner stopped at 0011, which made a fresh Docker/PostgreSQL deployment
        # structurally older than the application code.  Explicit ordering is intentional
        # because 0016 and 0017 each have two independent migrations.
        remaining_migrations = [
            ("0012_personnel_domain", "0012_personnel_domain.sql"),
            ("0013_schooling_domain", "0013_schooling_domain.sql"),
            ("0014_preservation_school_identity_and_enrollment", "0014_preservation_school_identity_and_enrollment.sql"),
            ("0015_effectifs_depots_domain", "0015_effectifs_depots_domain.sql"),
            ("0016_documents_domain", "0016_documents_domain.sql"),
            ("0016_finance_checkout", "0016_finance_checkout.sql"),
            ("0017_checkout_sequences_anticipation", "0017_checkout_sequences_anticipation.sql"),
            ("0017_documents_logical_current", "0017_documents_logical_current.sql"),
            ("0018_finance_other_collections_inventory", "0018_finance_other_collections_inventory.sql"),
            ("0019_finance_recovery_regularizations", "0019_finance_recovery_regularizations.sql"),
            ("0020_recovery_class_register", "0020_recovery_class_register.sql"),
            ("0021_finance_cash_industrial", "0021_finance_cash_industrial.sql"),
            ("0021_finance_report_templates", "0021_finance_report_templates.sql"),
            ("0022_finance_controls", "0022_finance_controls.sql"),
            ("0023_fee_tracking", "0023_fee_tracking.sql"),
            ("0024_stewardship_industrial", "0024_stewardship_industrial.sql"),
            ("0025_communications_industrial", "0025_communications_industrial.sql"),
            ("0026_persistent_device_sessions", "0026_persistent_device_sessions.sql"),
            ("0027_performance_indexes", "0027_performance_indexes.sql"),
            ("0028_scalability_query_indexes", "0028_scalability_query_indexes.sql"),
            ("0029_keyset_journal_indexes", "0029_keyset_journal_indexes.sql"),
            ("0030_worker_recovery_leases", "0030_worker_recovery_leases.sql"),
            ("0031_platform_system_notifications", "0031_platform_system_notifications.sql"),
            ("0032_platform_access_governance", "0032_platform_access_governance.sql"),
            ("0033_student_import_staging", "0033_student_import_staging.sql"),
            ("0034_staff_import_staging", "0034_staff_import_staging.sql"),
            ("0035_financial_history_import", "0035_financial_history_import.sql"),
            ("0036_platform_collaborator_role", "0036_platform_collaborator_role.sql"),
            ("0037_rbac_nullable_root_scopes", "0037_rbac_nullable_root_scopes.sql"),
            ("0038_school_bootstrap_insert_only", "0038_school_bootstrap_insert_only.sql"),
            ("0039_platform_supervision_read", "0039_platform_supervision_read.sql"),
            ("0040_finance_view_invoker", "0040_finance_view_invoker.sql"),
            ("0041_finance_tenant_grants", "0041_finance_tenant_grants.sql"),
            ("0042_tenant_membership_deactivation", "0042_tenant_membership_deactivation.sql"),
            ("0043_finance_charge_capacity_guard", "0043_finance_charge_capacity_guard.sql"),
            ("0044_owner_decision_personnel_roles", "0044_owner_decision_personnel_roles.sql"),
            ("0045_finance_read_model_performance", "0045_finance_read_model_performance.sql"),
            ("0046_session_lifetime_rotation", "0046_session_lifetime_rotation.sql"),
            ("0047_platform_first_manager_setup", "0047_platform_first_manager_setup.sql"),
            ("0048_document_object_storage", "0048_document_object_storage.sql"),
            ("0049_finance_family_basket", "0049_finance_family_basket.sql"),
            ("0050_receipt_printing", "0050_receipt_printing.sql"),
            ("0051_persistent_sessions_worker_role", "0051_persistent_sessions_worker_role.sql"),
            ("0052_platform_governance", "0052_platform_governance.sql"),
            ("0053_school_suspension_effects", "0053_school_suspension_effects.sql"),
            ("0054_platform_audit_indexes", "0054_platform_audit_indexes.sql"),
            ("0055_notifications_center", "0055_notifications_center.sql"),
            ("0056_platform_mfa_totp", "0056_platform_mfa_totp.sql"),
            ("0057_mfa_step_up_school_context", "0057_mfa_step_up_school_context.sql"),
            ("0058_school_user_management", "0058_school_user_management.sql"),
            ("0059_class_status_desktop_parity", "0059_class_status_desktop_parity.sql"),
            ("0060_tariff_rules_desktop_parity", "0060_tariff_rules_desktop_parity.sql"),
            ("0061_fee_schedules_charge_generation", "0061_fee_schedules_charge_generation.sql"),
            ("0062_benefit_policies_desktop_parity", "0062_benefit_policies_desktop_parity.sql"),
            ("0063_admission_conditions_desktop_parity", "0063_admission_conditions_desktop_parity.sql"),
            ("0064_payment_policy_desktop_parity", "0064_payment_policy_desktop_parity.sql"),
            ("0065_receipt_settings_desktop_parity", "0065_receipt_settings_desktop_parity.sql"),
            ("0066_anticipation_plans_desktop_parity", "0066_anticipation_plans_desktop_parity.sql"),
            ("0067_admin_school_anticipation_plans", "0067_admin_school_anticipation_plans.sql"),
            ("0068_n3a_role_governance", "0068_n3a_role_governance.sql"),
            ("0069_n3b_cash_integrity", "0069_n3b_cash_integrity.sql"),
            ("0070_n3c_financial_decisions", "0070_n3c_financial_decisions.sql"),
            ("0071_n3d_advance_funds", "0071_n3d_advance_funds.sql"),
            ("0072_n3e_checkout_sequence", "0072_n3e_checkout_sequence.sql"),
            ("0073_n3f_payroll_deductions", "0073_n3f_payroll_deductions.sql"),
            ("0074_n3g_periodic_reports", "0074_n3g_periodic_reports.sql"),
            ("0075_n3h_schooling_parity", "0075_n3h_schooling_parity.sql"),
            ("0076_external_messaging", "0076_external_messaging.sql"),
            ("0077_user_avatars", "0077_user_avatars.sql"),
            ("0078_schools_directory", "0078_schools_directory.sql"),
            ("0079_identities_directory", "0079_identities_directory.sql"),
            ("0080_platform_capability_grants", "0080_platform_capability_grants.sql"),
            ("0081_notification_campaigns_history", "0081_notification_campaigns_history.sql"),
            ("0082_audit_log_search", "0082_audit_log_search.sql"),
            ("0083_platform_alerts", "0083_platform_alerts.sql"),
            ("0084_platform_messaging_cockpit", "0084_platform_messaging_cockpit.sql"),
            ("0085_school_rbac_policies", "0085_school_rbac_policies.sql"),
            ("0086_school_identity_tenant_update", "0086_school_identity_tenant_update.sql"),
            ("0087_benefit_policies_multi_fee", "0087_benefit_policies_multi_fee.sql"),
            ("0088_settings_documents_backups_diagnostics", "0088_settings_documents_backups_diagnostics.sql"),
            ("0089_admin_finition_plans_years", "0089_admin_finition_plans_years.sql"),
            ("0090_caissier_secretariat_imports", "0090_caissier_secretariat_imports.sql"),
            ("0091_caissier_mouvements_effectifs", "0091_caissier_mouvements_effectifs.sql"),
            ("0092_tuition_alias_minerval_sequence", "0092_tuition_alias_minerval_sequence.sql"),
            ("0093_offline_cash_active", "0093_offline_cash_active.sql"),
            ("0094_receipt_print_queue", "0094_receipt_print_queue.sql"),
            ("0095_official_report_archive_idempotency", "0095_official_report_archive_idempotency.sql"),
            ("0096_gestionnaire_no_cash_day_close", "0096_gestionnaire_no_cash_day_close.sql"),
            ("0097_promoteur_finance_no_history_execute", "0097_promoteur_finance_no_history_execute.sql"),
            ("0098_responsable_finance_headcounts", "0098_responsable_finance_headcounts.sql"),
            ("0099_stewardship_asset_update_event", "0099_stewardship_asset_update_event.sql"),
            ("0100_intendance_capabilities_active", "0100_intendance_capabilities_active.sql"),
            ("0101_inventory_movements_recent_index", "0101_inventory_movements_recent_index.sql"),
            ("0102_directors_personnel_read", "0102_directors_personnel_read.sql"),
            ("0103_documents_print_removed", "0103_documents_print_removed.sql"),
            ("0104_enrollments_export_active", "0104_enrollments_export_active.sql"),
            ("0105_finance_annual_exigibility", "0105_finance_annual_exigibility.sql"),
        ]
        # CI only (rbac-contract job): stop after a given migration to snapshot the state BEFORE a later one.
        until = os.environ.get("EDUSYNC_MIGRATE_UNTIL", "").strip()
        for version, filename in remaining_migrations:
            if not _migration_applied(conn, version):
                _execute_sql_file(conn, MIGRATIONS / filename)
                _record_migration(conn, version)
            if until and version == until:
                break

        dbname = owner_url.database or "edusync"
        conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE \"{dbname.replace(chr(34), chr(34)*2)}\" TO {TENANT_ROLE}, {PLATFORM_ROLE}")
        conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {TENANT_ROLE}, {PLATFORM_ROLE}")
        conn.exec_driver_sql("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        conn.exec_driver_sql("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC")

        conn.exec_driver_sql(
            f"GRANT SELECT ON schools, users, school_memberships, membership_roles, "
            f"roles, permissions, role_permissions TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(f"GRANT SELECT, INSERT ON audit_events TO {TENANT_ROLE}")
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE ON outbox_events, idempotency_registry, sync_conflicts TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON notifications, devices, sync_inbox, sync_cursors TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE ON push_subscriptions TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE ON offline_finance_leases, offline_receipt_counters, "
            f"offline_receipt_tokens, offline_charge_snapshots, offline_payment_inbox, "
            f"offline_charge_reservations, offline_finance_incidents TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT ON capability_catalog TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON rbac_roles, rbac_role_capabilities, "
            f"rbac_assignments, rbac_assignment_scopes, rbac_exception_grants TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT ON rdc_reference_sections, rdc_reference_classes, rdc_reference_fee_types TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON settings_bootstrap_state, academic_years, school_sections, "
            f"school_options, school_classes, fee_types, tariffs, school_policy_documents, contribution_types, "
            f"school_products TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT INSERT ON settings_bootstrap_state, school_policy_documents TO {PLATFORM_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE ON student_import_batches, student_import_rows, "
            f"staff_import_batches, staff_import_rows, financial_history_import_batches, "
            f"financial_history_import_rows TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT ON financial_history_import_ledger TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE ON finance_cash_sessions TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT ON finance_cash_expenses, finance_cash_events TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT ON finance_charge_effective, finance_charges, finance_decisions, "
            f"finance_charge_regularizations, fee_categories TO {TENANT_ROLE}"
        )
        conn.exec_driver_sql(f"GRANT INSERT ON finance_charge_regularizations TO {TENANT_ROLE}")
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT ON platform_system_notifications TO {PLATFORM_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT SELECT (status, attempts) ON communication_deliveries TO {PLATFORM_ROLE}"
        )
        conn.exec_driver_sql(
            f"GRANT EXECUTE ON FUNCTION next_offline_receipt_no(uuid), "
            f"assert_finance_writer_allowed(uuid,uuid,uuid,uuid,uuid), "
            f"assert_finance_charge_writer_allowed(uuid,uuid,uuid), "
            f"resolve_offline_finance_quarantine(uuid,uuid,text) TO {TENANT_ROLE}"
        )

        platform_dml = [
            "schools", "users", "school_memberships", "membership_roles", "audit_events",
            "outbox_events", "notifications", "devices", "sync_inbox", "sync_cursors",
            "idempotency_registry", "sync_conflicts",
            "offline_finance_leases", "offline_receipt_counters", "offline_receipt_tokens",
            "offline_charge_snapshots", "offline_payment_inbox",
            "offline_charge_reservations", "offline_finance_incidents",
            "rbac_roles", "rbac_role_capabilities",
            "rbac_assignments", "rbac_assignment_scopes", "rbac_exception_grants",
            "platform_account_status", "push_subscriptions",
        ]
        conn.exec_driver_sql(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {', '.join(platform_dml)} TO {PLATFORM_ROLE}"
        )
        conn.exec_driver_sql(f"GRANT SELECT ON capability_catalog TO {PLATFORM_ROLE}")
        conn.exec_driver_sql(f"GRANT SELECT ON platform_reserved_capabilities TO {PLATFORM_ROLE}")
        conn.exec_driver_sql(f"REVOKE UPDATE, DELETE ON audit_events FROM {PLATFORM_ROLE}")
        # Second factor (0056): reachable by the platform role only, revoked but never erased; nothing for tenants.
        conn.exec_driver_sql(f"REVOKE DELETE, TRUNCATE ON user_mfa_factors, user_mfa_recovery_codes, mfa_challenges FROM {PLATFORM_ROLE}")
        conn.exec_driver_sql(f"REVOKE ALL ON user_mfa_factors, user_mfa_recovery_codes, mfa_challenges FROM {TENANT_ROLE}")
        conn.exec_driver_sql(f"GRANT SELECT ON roles, permissions, role_permissions TO {PLATFORM_ROLE}")

        if worker_url is not None:
            # Queue tables only (see migration 0051). Re-applied on every run so an existing database gains the
            # worker role even when 0051 ran before the role existed.
            conn.exec_driver_sql(f"GRANT CONNECT ON DATABASE \"{dbname.replace(chr(34), chr(34)*2)}\" TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT USAGE ON SCHEMA public TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT SELECT, UPDATE ON outbox_events TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"REVOKE INSERT, DELETE ON outbox_events FROM {WORKER_ROLE}")
            # External messaging (0076): the worker dispatches requested messages into deliveries (INSERT), updates their
            # state, moves SMS credits through school_sms_wallet_apply and applies provider receipts. Never DELETE.
            conn.exec_driver_sql(f"GRANT SELECT, INSERT, UPDATE ON communication_deliveries TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT SELECT, UPDATE ON communication_messages, communication_recipients TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT SELECT ON communication_settings TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT SELECT, INSERT, UPDATE ON school_sms_wallets TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT SELECT, INSERT ON school_sms_ledger TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT SELECT, UPDATE ON push_subscriptions, provider_receipts TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"REVOKE DELETE ON communication_deliveries, communication_messages, communication_recipients, "
                                 f"school_sms_wallets, school_sms_ledger, push_subscriptions, provider_receipts FROM {WORKER_ROLE}")
            # Only the status of a school (suspended school => SMS held) and its name (e-mail / push titles), never contacts.
            conn.exec_driver_sql(f"GRANT SELECT (id, status) ON schools TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT SELECT (name) ON schools TO {WORKER_ROLE}")
            conn.exec_driver_sql(f"GRANT EXECUTE ON FUNCTION school_sms_wallet_apply(uuid,text,integer,text,uuid,text,uuid,text,text,text,text,numeric,text,numeric,text) TO {WORKER_ROLE}")
            for name in ("0051_persistent_sessions_worker_role.sql", "0053_school_suspension_effects.sql"):
                sql = (MIGRATIONS / name).read_text(encoding="utf-8")
                conn.exec_driver_sql(sql[sql.index("DO $$"):], execution_options={"no_parameters": True})  # policies only

        conn.exec_driver_sql("ALTER TABLE idempotency_registry VALIDATE CONSTRAINT idempotency_scope_school_consistency")

        rows = conn.execute(text("""
            SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolbypassrls
              FROM pg_roles WHERE rolname IN (:tenant, :platform)
        """), {"tenant": TENANT_ROLE, "platform": PLATFORM_ROLE}).all()
        if len(rows) != 2:
            raise RuntimeError("Rôles PostgreSQL applicatifs incomplets")
        for row in rows:
            if any(bool(x) for x in row[1:]):
                raise RuntimeError(f"Rôle PostgreSQL trop privilégié: {row[0]}")

    print("POINT-4A database provisioning: PASS")


if __name__ == "__main__":
    main()

