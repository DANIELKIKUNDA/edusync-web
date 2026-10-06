"""Regression tests for defects reproduced live during the 2026-09-30 certification (D1-D5).

Live evidence (real PostgreSQL + HTTP): certification/claude-20260930/*.json.
These tests pin the fixes without a database: checkout logic runs against a scripted connection,
and SQL privilege contracts are asserted on the migrations themselves.
"""
from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from edusync.adapters.postgres_finance_checkout import PostgresFinanceCheckoutRepository

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "migrations"


class _Result:
    def __init__(self, rows=None, scalar=None):
        self._rows, self._scalar = rows or [], scalar

    def mappings(self):
        return self

    def first(self):
        return self._rows[0] if self._rows else None

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._scalar


class ScriptedConnection:
    """Answers the SQL issued by collect(); records every write."""

    def __init__(self, charges, existing_payment=None, adjustments=None):
        self.charges, self.existing, self.writes, self.locks = charges, existing_payment, [], []
        self.adjustments = adjustments or {}  # charge id -> (decisions, outside_cash)

    def execute(self, stmt, params=None):
        sql = " ".join(str(stmt).split())
        if "pg_advisory_xact_lock" in sql:
            self.locks.append(params["k"])
            return _Result()
        if sql.startswith("SELECT id,receipt_number") and "FROM finance_payments" in sql:
            return _Result([self.existing] if self.existing else [])
        if "FROM finance_cash_sessions" in sql:
            return _Result(scalar=str(uuid4()))
        if sql.startswith("SELECT * FROM finance_charges"):
            return _Result(self.charges)
        if "outside_cash" in sql and "finance_charge_regularizations" in sql:
            return _Result([{"id": c, "decisions": d, "outside_cash": o} for c, (d, o) in self.adjustments.items()])
        if sql.startswith(("INSERT", "UPDATE")):
            self.writes.append((sql.split("(")[0], params))
            return _Result()
        raise AssertionError(f"unexpected SQL: {sql[:120]}")


def _charge(currency, net, label):
    return {"id": str(uuid4()), "label": label, "currency": currency, "net_amount": Decimal(net), "paid_amount": Decimal("0"),
            "periodicity": "ONE_OFF", "period_label": None, "period_order": None, "sequence_group": None, "sequence_order": None}


SID, UID, MID, EID = uuid4(), uuid4(), uuid4(), uuid4()


def test_d2_cdf_payment_allowed_when_enrollment_also_owes_usd():
    cdf, usd = _charge("CDF", "1000", "Minerval"), _charge("USD", "20", "Inscription")
    conn = ScriptedConnection([cdf, usd])
    out = PostgresFinanceCheckoutRepository(conn).collect(SID, UID, MID, EID, [UUID(cdf["id"])], Decimal("400"), "CDF", "k-d2")
    assert out["replayed"] is False and out["allocations"] == [{"label": "Minerval", "amount": "400"}]
    assert sum(1 for w in conn.writes if w[0].startswith("INSERT INTO finance_payments")) == 1


def test_d2_currency_must_still_match_the_selected_charge():
    usd = _charge("USD", "20", "Inscription")
    with pytest.raises(ValueError, match="Devise"):
        PostgresFinanceCheckoutRepository(ScriptedConnection([usd])).collect(SID, UID, MID, EID, [UUID(usd["id"])], Decimal("5"), "CDF", "k")


def test_d4_replay_with_same_payload_returns_original_receipt_without_writes():
    existing = {"id": uuid4(), "receipt_number": "REC-1", "amount": Decimal("400.00"), "currency": "CDF", "enrollment_id": EID}
    conn = ScriptedConnection([], existing)
    out = PostgresFinanceCheckoutRepository(conn).collect(SID, UID, MID, EID, [uuid4()], Decimal("400"), "CDF", "k-d4")
    assert out["replayed"] is True and out["receipt_number"] == "REC-1" and "enrollment_id" not in out
    assert conn.writes == []


@pytest.mark.parametrize("change", [{"amount": Decimal("401")}, {"currency": "USD"}, {"enrollment_id": uuid4()}])
def test_d4_reused_key_with_different_payload_is_rejected(change):
    existing = {"id": uuid4(), "receipt_number": "REC-1", "amount": Decimal("400"), "currency": "CDF", "enrollment_id": EID, **change}
    conn = ScriptedConnection([], existing)
    with pytest.raises(ValueError, match="Idempotency-Key"):
        PostgresFinanceCheckoutRepository(conn).collect(SID, UID, MID, EID, [uuid4()], Decimal("400"), "CDF", "k-d4")
    assert conn.writes == []


def test_d3_same_key_is_serialised_before_the_replay_lookup():
    conn = ScriptedConnection([], {"id": uuid4(), "receipt_number": "R", "amount": Decimal("1"), "currency": "CDF", "enrollment_id": EID})
    PostgresFinanceCheckoutRepository(conn).collect(SID, UID, MID, EID, [uuid4()], Decimal("1"), "CDF", "k-d3")
    assert conn.locks == [f"finance-payment:{SID}:k-d3"]


def _sql(name):
    """Migration statements without comments (prose must not satisfy or break a contract)."""
    lines = (MIG / name).read_text(encoding="utf-8").splitlines()
    return "\n".join(line for line in lines if not line.lstrip().startswith("--"))


def test_d1_finance_ledger_is_granted_to_tenant_but_stays_append_only():
    s = _sql("0041_finance_tenant_grants.sql")
    assert "GRANT SELECT, INSERT ON finance_payments, finance_payment_allocations TO edusync_tenant" in s
    assert "REVOKE UPDATE, DELETE ON finance_payments, finance_payment_allocations FROM edusync_tenant" in s
    # tariff / net amount never writable by the tenant: only the paid counter
    assert "GRANT UPDATE (paid_amount, updated_at) ON finance_charges TO edusync_tenant" in s
    assert not re.search(r"GRANT[^;]*\bDELETE\b[^;]*TO edusync_tenant", s)
    assert not re.search(r"GRANT UPDATE ON finance_(payments|charges)", s)


def test_d5_tenant_may_only_deactivate_memberships():
    s = _sql("0042_tenant_membership_deactivation.sql")
    assert "GRANT UPDATE (active, version) ON school_memberships TO edusync_tenant" in s
    assert "AS RESTRICTIVE FOR UPDATE TO edusync_tenant" in s and "WITH CHECK (active = false)" in s
    assert "school_id" not in s.split("GRANT UPDATE", 1)[1].split(";", 1)[0]


# --- Sessions (D6-D8), reproduced live in certification/claude-20260930/sessions-live.json -------
SRC = ROOT / "src" / "edusync"


def test_d6_access_tokens_are_bound_to_a_live_device_session():
    iam = (SRC / "modules/iam/api/router.py").read_text(encoding="utf-8")
    deps = (SRC / "bootstrap/dependencies.py").read_text(encoding="utf-8")
    # platform login, school login and refresh all embed the device session id
    assert iam.count('"sid": str(session_id)') == 2 and "'sid':str(row['id'])" in iam
    # Closure 2026-10: both logins create their device session through one helper (with server-side expiry).
    assert iam.count("_new_device_session(conn, services.settings") == 2 and "RETURNING id,expires_at" in iam
    # both actor resolvers reject a token whose session was revoked (logout / device revocation)
    assert deps.count("_assert_device_session_live(conn, claims, user_id)") == 2
    assert "revoked_at IS NULL" in deps


def test_d6_token_without_session_claim_is_rejected():
    from fastapi import HTTPException
    from edusync.bootstrap.dependencies import _assert_device_session_live
    with pytest.raises(HTTPException) as e:
        _assert_device_session_live(object(), {"sub": "x"}, uuid4())
    assert e.value.status_code == 401


def test_d6_revoked_session_is_rejected():
    from fastapi import HTTPException
    from edusync.bootstrap.dependencies import _assert_device_session_live

    class Conn:
        def execute(self, *_a, **_k):
            return _Result([])

    with pytest.raises(HTTPException) as e:
        _assert_device_session_live(Conn(), {"sid": str(uuid4())}, uuid4())
    assert e.value.status_code == 401


def test_d7_session_revocation_id_is_validated_as_uuid():
    import inspect
    from edusync.modules.iam.api.router import revoke_session
    assert inspect.signature(revoke_session).parameters["session_id"].annotation in (UUID, "UUID")


def test_d8_successful_login_only_clears_the_account_counter():
    from edusync.shared.infrastructure.login_guard import LoginAttemptGuard

    class FakeRedis:
        def __init__(self):
            self.deleted = []

        def delete(self, *keys):
            self.deleted.extend(keys)

    g = LoginAttemptGuard.__new__(LoginAttemptGuard)
    g.redis = FakeRedis()
    acct, ip = g._keys("a@b.c", "10.0.0.1")
    g.success("a@b.c", "10.0.0.1")
    assert g.redis.deleted == [acct] and ip not in g.redis.deleted


# --- D11: the cash desk only collects what is still owed (decisions + outside-cash regularizations) --
def test_d11_charge_settled_outside_cash_cannot_be_collected_again():
    ch = _charge("CDF", "30000", "Minerval")
    conn = ScriptedConnection([ch], adjustments={ch["id"]: (Decimal("0"), Decimal("30000"))})
    with pytest.raises(ValueError):
        PostgresFinanceCheckoutRepository(conn).collect(SID, UID, MID, EID, [UUID(ch["id"])], Decimal("30000"), "CDF", "k-d11")
    assert not [w for w in conn.writes if "finance_payments" in w[0]]


def test_d11_exemption_reduces_what_can_be_collected():
    ch = _charge("CDF", "30000", "Minerval")
    conn = ScriptedConnection([ch], adjustments={ch["id"]: (Decimal("10000"), Decimal("0"))})
    repo = PostgresFinanceCheckoutRepository(conn)
    with pytest.raises(ValueError):  # 30 000 > 20 000 still owed and no anticipation plan
        repo.collect(SID, UID, MID, EID, [UUID(ch["id"])], Decimal("30000"), "CDF", "k-d11b")
    out = repo.collect(SID, UID, MID, EID, [UUID(ch["id"])], Decimal("20000"), "CDF", "k-d11c")
    assert out["allocations"] == [{"label": "Minerval", "amount": "20000"}]


def test_d11_database_guard_blocks_receiving_more_than_the_obligation():
    s = _sql("0043_finance_charge_capacity_guard.sql")
    assert "AFTER INSERT ON finance_payment_allocations" in s and "AFTER INSERT ON finance_charge_regularizations" in s
    assert "FOR UPDATE" in s and "ERRCODE = 'check_violation'" in s and "SECURITY INVOKER" in s


def test_d9_d10_imports_revalidate_under_lock_at_execution():
    r = (SRC / "modules/migration_import/api/router.py").read_text(encoding="utf-8")
    assert r.count("raise HTTPException(409,STALE_ANALYSIS") >= 4
    assert "FOR UPDATE OF fc" in r and "_same_file_duplicates" in r


# --- D12: unconsumed outbox envelopes must not exhaust Redis ------------------------------------
def test_d12_outbox_transport_queue_is_capped_atomically():
    from edusync.modules.sync import outbox_worker as ow

    class Pipe:
        def __init__(self):
            self.ops = []

        def lpush(self, *a):
            self.ops.append(("lpush",) + a)

        def ltrim(self, *a):
            self.ops.append(("ltrim",) + a)

        def execute(self):
            return [1, True]

    class R:
        def __init__(self):
            self.p = Pipe()

        def pipeline(self, transaction=True):
            assert transaction is True
            return self.p

    class Eng:
        def begin(self):
            class C:
                def __enter__(s):
                    return s

                def __exit__(s, *a):
                    return False

                def execute(s, *a, **k):
                    return None
            return C()

    r = R()
    assert ow.publish_claim(Eng(), r, {"id": uuid4(), "payload": {}, "attempts": 0}, "t") is True
    assert [o[0] for o in r.p.ops] == ["lpush", "ltrim"] and r.p.ops[1][1:] == (ow.QUEUE, 0, ow.MAX_QUEUE_LENGTH - 1)


# --- D13: login must not reveal which accounts exist through timing ----------------------------
def test_d13_unknown_account_still_runs_an_argon2_verification():
    iam = (SRC / "modules/iam/api/router.py").read_text(encoding="utf-8")
    assert "_DUMMY_PASSWORD_HASH = hash_password(" in iam
    assert "user.password_hash if user is not None else _DUMMY_PASSWORD_HASH" in iam
    from edusync.modules.iam.api import router as r
    assert r._DUMMY_PASSWORD_HASH.startswith("$argon2") and not r.verify_password("x" * 12, r._DUMMY_PASSWORD_HASH)


# --- D14: Excel formula injection (CWE-1236) -------------------------------------------------------
def test_d14_user_data_starting_with_equals_is_exported_as_text():
    from io import BytesIO
    from openpyxl import Workbook, load_workbook
    from edusync.shared.infrastructure.xlsx_safety import neutralize_formulas
    wb = Workbook()
    wb.active["A1"] = '=HYPERLINK("http://evil.example","Payer")'
    neutralize_formulas(wb)
    out = BytesIO()
    wb.save(out)
    cell = load_workbook(BytesIO(out.getvalue())).active["A1"]
    assert cell.data_type == "s" and cell.value.startswith("=HYPERLINK")


def test_d14_every_workbook_save_is_protected():
    import re
    unprotected = []
    for f in SRC.rglob("*.py"):
        t = f.read_text(encoding="utf-8")
        for line in t.splitlines():
            if re.search(r"\bwb\.save\(", line) and "neutralize_formulas(wb)" not in line:
                unprotected.append(f"{f.name}: {line.strip()[:60]}")
            if "xlsxwriter.Workbook(" in line and "XLSXWRITER_OPTIONS" not in line:
                unprotected.append(f"{f.name}: {line.strip()[:60]}")
    assert not unprotected, unprotected


def test_d14_xlsxwriter_never_converts_strings_to_formulas():
    from edusync.shared.infrastructure.xlsx_safety import XLSXWRITER_OPTIONS
    assert XLSXWRITER_OPTIONS["strings_to_formulas"] is False


# --- D15: real client IP behind the reverse proxy --------------------------------------------------
def test_d15_backend_trusts_forwarded_ip_only_from_proxy_and_hides_server_header():
    root = ROOT.parent
    docker = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (root / "docker-compose.yml").read_text(encoding="utf-8")
    assert '"--proxy-headers"' in docker and '"--no-server-header"' in docker
    backend = compose.split("  backend:", 1)[1].split("  frontend:", 1)[0]
    assert "FORWARDED_ALLOW_IPS:" in backend and '"127.0.0.1:8000:8000"' in backend


# --- D16: recovery read models must read the canonical obligation view ----------------------------
def test_d16_every_query_using_effective_net_amount_reads_the_view():
    import re
    bad = []
    for f in SRC.rglob("*.py"):
        for q in re.findall(r'"""(.*?)"""', f.read_text(encoding="utf-8"), re.S):
            if "effective_net_amount" in q and "finance_charge_effective" not in q:
                bad.append(f"{f.name}: {' '.join(q.split())[:80]}")
    assert not bad, bad


def test_d16_recovery_aggregates_alias_effective_amount_as_net_amount():
    s = (SRC / "adapters/postgres_finance_recovery.py").read_text(encoding="utf-8")
    assert s.count("fc.effective_net_amount net_amount") == 4
    assert "JOIN finance_charges fc" not in s


# --- D17: global staff history never rendered (missing bind parameter + literal "{extra}") --------
def test_d17_status_history_binds_offset_and_has_no_template_leftover():
    from edusync.adapters.postgres_personnel import PostgresPersonnelRepository

    seen = {}

    class Conn:
        def execute(self, stmt, args=None):
            seen["sql"], seen["args"] = str(stmt), dict(args or {})

            class R:
                def all(self):
                    return []
            return R()

    class AllVisible(PostgresPersonnelRepository):
        def _visible_staff_ids(self, *_a, **_k):
            return None

    repo = AllVisible(Conn())
    repo.list_status_history(uuid4(), scopes=(("SCHOOL", None),), limit=10, offset=20)
    assert seen["args"]["offset"] == 20 and "{extra}" not in seen["sql"] and ":offset" in seen["sql"]


# --- D18-D20: Intendance stock ledger integrity --------------------------------------------------
def test_d18_stock_movement_is_idempotent():
    s = (SRC / "modules/stewardship/api/router.py").read_text(encoding="utf-8")
    assert "operation='STEWARDSHIP_STOCK_MOVEMENT'" in s and "Idempotency-Key obligatoire" in s


def test_d19_count_validation_applies_variance_to_current_stock():
    s = (SRC / "modules/stewardship/api/router.py").read_text(encoding="utf-8")
    block = s.split("def count_validate", 1)[1]
    assert "SET quantity=quantity+:d" in block and "FOR UPDATE" in block
    assert "SET quantity=:q" not in block  # never overwrite with the (possibly stale) counted value


def test_d20_validated_count_is_immutable():
    s = (SRC / "modules/stewardship/api/router.py").read_text(encoding="utf-8")
    block = s.split("def count_line", 1)[1].split("def count_validate", 1)[0]
    assert "status FROM inventory_counts" in block and "state!='DRAFT'" in block


# --- Owner decision 2026-10-02: personnel mutations for standard roles -----------------------------
def test_owner_decision_personnel_roles():
    s = _sql("0044_owner_decision_personnel_roles.sql")
    gest = {"personnel.create", "personnel.update", "personnel.assignments.add", "personnel.assignments.end", "personnel.functions.manage", "personnel.exit"}
    for cap in gest:
        assert f"('GESTIONNAIRE', '{cap}')" in s
    assert "('SECRETARIAT',  'personnel.create')" in s and "('SECRETARIAT',  'personnel.update')" in s
    assert "('SECRETARIAT',  'personnel.exit')" not in s
    assert "personnel.reactivate" not in s  # reactivation restores access: custom roles only
    for excluded in ("PROMOTEUR", "ADMIN_SYSTEME_ECOLE", "RESPONSABLE_FINANCE"):
        assert f"('{excluded}'" not in s


# --- School access governance (owner decision 2026-10-02): guardrails are server-side -------------
def test_access_governance_guardrails_are_enforced_server_side():
    s = (SRC / "modules/access/api/router.py").read_text(encoding="utf-8")
    assert "personne ne peut s'attribuer des droits à soi-même" in s          # no self-service grant
    assert "personne ne modifie ses propres droits" in s                       # no self-service revoke
    assert "vous ne pouvez pas modifier un rôle que vous détenez" in s         # no editing a role you hold
    assert "code NOT LIKE 'platform.%'" in s                                   # no platform capability
    assert s.count("_assert_managers_remain(conn, actor.school_id)") == 2      # never zero access managers
    assert "Les rôles standards ne se modifient pas" in s                      # standard roles immutable
    assert s.count("_idempotent(services, actor, idempotency_key") == 5        # every mutation idempotent
    assert s.count('_audit(conn, actor, "ACCESS_') == 5                        # every mutation journaled


def test_access_names_resolved_only_for_this_schools_members():
    s = (SRC / "modules/access/api/router.py").read_text(encoding="utf-8")
    assert "def _user_cards" in s and "WHERE id=ANY(CAST(:ids AS uuid[]))" in s
    assert "JOIN users" not in s.split("def members", 1)[1].split("def scope_options", 1)[0]


def test_access_screen_is_wired_into_school_navigation():
    app = (ROOT.parent / "frontend/src/App.tsx").read_text(encoding="utf-8")
    # Closure 2026-10: navigation icons are SVG keys, no emoji.
    assert "['lock','Accès & rôles','access']" in app and "access:['access.roles.read','audit.school.read']" in app
    assert "module==='access'?<AccessPage" in app
    main = (SRC / "bootstrap/app.py").read_text(encoding="utf-8")
    assert 'prefix="/api/v1/access"' in main


def test_d21_finance_read_models_aggregate_once_instead_of_per_charge():
    # Measured on 132 000 charges: correlated sums ran 120 004 times per screen (10 s to 28 s).
    mig = (ROOT / "migrations/0045_finance_read_model_performance.sql").read_text(encoding="utf-8")
    view = mig.split("CREATE OR REPLACE VIEW finance_charge_effective", 1)[1].split(";", 1)[0]
    assert "WITH (security_invoker = true)" in view                  # tenant RLS still applies
    assert "(SELECT sum(" not in view and "GROUP BY school_id, charge_id, currency" in view
    assert "status = 'ACTIVE'" in view and "d.currency = fc.currency" in view
    cols = re.findall(r"AS (\w+)", view.split("FROM finance_charges fc", 1)[0])
    assert cols == ["effective_net_amount", "decision_amount", "outside_cash_amount"]  # appended, order kept
    for name in ("postgres_finance_recovery.py", "postgres_fee_tracking.py"):
        src = (SRC / "adapters" / name).read_text(encoding="utf-8")
        assert "finance_charge_regularizations" not in src and "fc.outside_cash_amount" in src
    prov = (ROOT / "scripts/provision_database.py").read_text(encoding="utf-8")
    assert '"0045_finance_read_model_performance.sql"' in prov


def test_d22_fee_tracking_detail_is_paged_server_side():
    # A whole school returned 12 003 lines (4 MB) per call and ignored ?limit: 24 s at 8 users.
    from edusync.modules.finance_fee_tracking.api import router as ft
    import inspect
    sig = inspect.signature(ft.students)
    assert sig.parameters["limit"].default.default == 200 and sig.parameters["offset"].default.default == 0
    src = (SRC / "modules/finance_fee_tracking/api/router.py").read_text(encoding="utf-8")
    assert "le=1000" in src and "students_page(" in src and "'total':total" in src
    repo = (SRC / "adapters/postgres_fee_tracking.py").read_text(encoding="utf-8")
    assert "count(*) OVER() total_rows" in repo and "LIMIT %s OFFSET %s" in repo
    assert "ft.label,s.id,ft.id" in repo                                # deterministic paging order
    ui = (ROOT.parent / "frontend/src/finance.tsx").read_text(encoding="utf-8")
    assert "limit:FEE_PAGE" in ui and "offset:rows.length" in ui


def test_u10_search_and_filter_fields_have_accessible_names():
    # Final browser sweep (112 screens) found 3 fields announced only by their placeholder.
    fin = (ROOT.parent / "frontend/src/finance.tsx").read_text(encoding="utf-8")
    assert fin.count('aria-label="Rechercher un élève ou une famille" placeholder="Nom, matricule, famille ou téléphone…"') == 2
    docs = (ROOT.parent / "frontend/src/documents.tsx").read_text(encoding="utf-8")
    # Closure 2026-10: documents page split into history and catalogue, each search field keeps an accessible name.
    assert 'aria-label="Rechercher dans les documents générés"' in docs and 'aria-label="Rechercher dans le catalogue"' in docs and 'aria-label="Filtrer par module"' in docs
