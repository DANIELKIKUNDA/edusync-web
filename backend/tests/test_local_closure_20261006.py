"""Regression tests for the local closure pass (2026-10-06).

Live proofs (real API + PostgreSQL + Redis + S3) are in certification/closure-20261006/*.json; these tests
lock the contracts without a database.
"""
from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "edusync"


# --- object storage ---------------------------------------------------------------------------------
def _aws_example():
    from edusync.shared.infrastructure.object_storage import S3CompatibleObjectStorage
    return S3CompatibleObjectStorage(endpoint="https://s3.amazonaws.com", access_key="AKIAIOSFODNN7EXAMPLE",
                                     secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY", bucket="examplebucket", path_style=False)


def test_sigv4_presigned_url_matches_official_aws_vector():
    s = _aws_example()
    q = {"X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": "AKIAIOSFODNN7EXAMPLE/20130524/us-east-1/s3/aws4_request",
         "X-Amz-Date": "20130524T000000Z", "X-Amz-Expires": "86400", "X-Amz-SignedHeaders": "host"}
    assert s._signature("GET", "/test.txt", q, {"host": "examplebucket.s3.amazonaws.com"}, "UNSIGNED-PAYLOAD", "20130524T000000Z")[1] == \
        "aeeed9bbccd4d02ee5c0109b86d86835f995330da4c265957d157751f604d404"


def test_sigv4_header_signature_matches_official_aws_vector():
    s = _aws_example()
    empty = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    h = {"host": "examplebucket.s3.amazonaws.com", "range": "bytes=0-9", "x-amz-content-sha256": empty, "x-amz-date": "20130524T000000Z"}
    assert s._signature("GET", "/test.txt", {}, h, empty, "20130524T000000Z")[1] == "f0e8bdb87c964420e857bd35b5d6ed310bd44f0170aba48dd91039c6036bdb41"


def test_presigned_links_are_short_lived_only():
    s = _aws_example()
    with pytest.raises(ValueError):
        s.presign_get("a/b.pdf", expires_seconds=7200)
    assert "X-Amz-Expires=300" in s.presign_get("a/b.pdf")


@pytest.mark.parametrize("key", ["../x", "/abs", "a//b", "a/./b", "a\\b", ""])
def test_object_keys_cannot_escape_their_prefix(key, tmp_path):
    from edusync.shared.infrastructure.object_storage import LocalObjectStorage
    with pytest.raises(ValueError):
        LocalObjectStorage(tmp_path).put(key, b"x", content_type="text/plain")


def test_storage_is_selected_by_configuration_only():
    from edusync.shared.infrastructure.object_storage import LocalObjectStorage, S3CompatibleObjectStorage, build_object_storage
    base = dict(object_storage_backend="auto", object_storage_endpoint="", object_storage_access_key="k", object_storage_secret_key="s",
                object_storage_bucket="b", object_storage_region="auto", object_storage_path_style=True, object_storage_local_root=".")
    assert build_object_storage(SimpleNamespace(**base)) is None
    assert isinstance(build_object_storage(SimpleNamespace(**{**base, "object_storage_endpoint": "https://x.r2.cloudflarestorage.com"})), S3CompatibleObjectStorage)
    assert isinstance(build_object_storage(SimpleNamespace(**{**base, "object_storage_backend": "local"})), LocalObjectStorage)
    src = (SRC / "shared/infrastructure/object_storage.py").read_text(encoding="utf-8").lower()
    assert "boto" not in src and "minio" not in src.replace("minio)", "")  # no vendor SDK dependency


# --- documents ----------------------------------------------------------------------------------------
def _png(size=(64, 64)):
    from PIL import Image
    b = BytesIO(); Image.new("RGB", size, (1, 2, 3)).save(b, "PNG"); return b.getvalue()


def test_logo_is_identified_by_content_not_by_declared_type():
    from edusync.modules.documents.application.object_store import validate_logo
    assert validate_logo(_png()) == ("image/png", "png")
    for bad in (b"", b"<svg onload=alert(1)>", b"\x89PNG\r\n\x1a\n" + b"0" * 50, _png((8, 8)), b"\x89PNG" + b"0" * 1_100_000):
        with pytest.raises(ValueError):
            validate_logo(bad)


def test_generators_never_read_a_server_file_path_for_the_logo():
    for rel in ("modules/effectifs/application/documents.py", "modules/schooling/application/documents.py"):
        s = (SRC / rel).read_text(encoding="utf-8")
        assert "logo_stream(school)" in s and "Path(str(v))" not in s and "Path(str(raw))" not in s


def test_logo_stream_refuses_a_key_outside_the_school_prefix():
    from edusync.modules.documents.application import object_store
    class Store:
        def get(self, key): return b"img"
    object_store.configure_storage(Store())
    try:
        assert object_store.logo_stream({"id": "s1", "logo_object_key": "schools/s2/branding/x.png"}) is None
        assert object_store.logo_stream({"id": "s1", "logo_object_key": "schools/s1/branding/x.png"}).read() == b"img"
    finally:
        object_store.configure_storage(None)


def test_signed_document_links_expire_and_resist_tampering():
    from edusync.modules.documents.application.object_store import sign_link, verify_link
    cfg = SimpleNamespace(document_link_secret="", jwt_secret="x" * 40, document_link_seconds=300)
    tok, exp = sign_link(cfg, document_id="d", school_id="s", user_id="u")
    assert verify_link(cfg, tok) == {"document_id": "d", "school_id": "s", "user_id": "u"} and exp - time.time() <= 300
    with pytest.raises(PermissionError):
        verify_link(cfg, tok[:-2] + ("AA" if not tok.endswith("AA") else "BB"))
    with pytest.raises(PermissionError):
        verify_link(cfg, sign_link(cfg, document_id="d", school_id="s", user_id="u", now=time.time() - 900)[0])
    with pytest.raises(PermissionError):
        verify_link(SimpleNamespace(document_link_secret="", jwt_secret="y" * 40, document_link_seconds=300), tok)


def test_safe_file_names():
    from edusync.modules.documents.application.object_store import safe_file_name
    assert safe_file_name("../../etc/passwd") == "etc_passwd"
    assert safe_file_name("Liste des élèves.PDF") == "Liste des eleves.pdf"
    assert "/" not in safe_file_name("a/b\\c.xlsx") and "\\" not in safe_file_name("a/b\\c.xlsx")


def test_archive_visibility_is_bound_to_the_producing_capability():
    from edusync.modules.documents.application.object_store import school_wide_capabilities
    from edusync.shared.application.context import ActorContext
    from uuid import uuid4
    a = ActorContext(uuid4(), uuid4(), uuid4(), frozenset({"students.directory.print_pdf", "personnel.directory.print_pdf"}),
                     capability_scopes=(("students.directory.print_pdf", "CLASS", "6A"), ("personnel.directory.print_pdf", "SCHOOL", None)))
    assert school_wide_capabilities(a) == ["personnel.directory.print_pdf"]
    router = (SRC / "modules/documents/api/router.py").read_text(encoding="utf-8")
    assert router.count("required_capability=ANY(CAST(:caps AS text[]))") == 2
    for rel in ("modules/schooling/api/router.py", "modules/personnel/api/router.py", "modules/effectifs/api/router.py", "modules/finance_recovery/api/router.py"):
        s = (SRC / rel).read_text(encoding="utf-8")
        assert s.count("archive_generated") - 1 == s.count("required_capability=")


# --- sessions / first-run setup -----------------------------------------------------------------------
def test_session_cookie_is_bounded_and_rotated():
    iam = (SRC / "modules/iam/api/router.py").read_text(encoding="utf-8")
    assert "persistent_session_cookie_days" not in iam
    assert "ROTATED_TOKEN_REUSED" in iam and "IDLE_TIMEOUT" in iam and "ABSOLUTE_EXPIRY" in iam
    assert "previous_valid_until=now()+make_interval(secs=>:grace)" in iam
    from edusync.bootstrap.settings import Settings
    s = Settings(jwt_secret="x" * 40)
    assert s.session_absolute_days == 90 and s.session_idle_days == 30 and s.session_rotation_grace_seconds <= 120
    deps = (SRC / "bootstrap/dependencies.py").read_text(encoding="utf-8")
    assert "revoked_at IS NULL AND expires_at>now()" in deps


def test_first_manager_setup_is_locked_and_token_gated():
    from edusync.modules.setup.api import router as setup
    req = lambda host: SimpleNamespace(client=SimpleNamespace(host=host))  # noqa: E731
    dev = SimpleNamespace(settings=SimpleNamespace(env="dev", setup_token=""))
    prod = SimpleNamespace(settings=SimpleNamespace(env="production", setup_token="t"))
    assert setup._token_required(dev, req("127.0.0.1")) is False
    assert setup._token_required(dev, req("::1")) is False
    assert setup._token_required(dev, req("10.0.0.7")) is True
    assert setup._token_required(prod, req("127.0.0.1")) is True
    src = (SRC / "modules/setup/api/router.py").read_text(encoding="utf-8")
    assert "pg_advisory_xact_lock" in src and "hmac.compare_digest" in src and "platform_setup_completion" in src
    mig = (ROOT / "migrations/0047_platform_first_manager_setup.sql").read_text(encoding="utf-8")
    assert "singleton boolean PRIMARY KEY" in mig and "REVOKE UPDATE, DELETE ON platform_setup_completion" in mig
    script = (ROOT / "scripts/bootstrap_platform_admin.py").read_text(encoding="utf-8")
    assert "_close_public_setup" in script


# --- SMS ----------------------------------------------------------------------------------------------
def test_sms_providers_are_resolved_by_code_and_test_providers_never_run_in_production():
    from edusync.modules.communications.providers import SandboxSmsProvider, provider_for
    dev = SimpleNamespace(env="dev", orange_sms_endpoint="", orange_sms_bearer_token="")
    prod = SimpleNamespace(env="production", orange_sms_endpoint="", orange_sms_bearer_token="")
    assert isinstance(provider_for(dev, "sandbox"), SandboxSmsProvider)
    assert provider_for(prod, "sandbox") is None and provider_for(prod, "mock") is None and provider_for(dev, "x") is None
    sb = SandboxSmsProvider()
    ok = sb.send_sms(destination="+243810001234", body="b", sender_id="S")
    assert ok.accepted and ok.provider_message_id and sb.delivery_report(ok.provider_message_id).status == "DELIVERED"
    assert sb.send_sms(destination="+243810000000", body="b", sender_id="S").error_code == "PROVIDER_REJECTED"
    assert sb.delivery_report(sb.send_sms(destination="+243810008888", body="b", sender_id="S").provider_message_id).status == "FAILED"


def test_sms_sent_requires_provider_proof_and_delivered_requires_a_report():
    w = (SRC / "modules/communications/worker.py").read_text(encoding="utf-8")
    assert "result.accepted and result.provider_message_id" in w
    assert "status='DELIVERED',delivered_at=now() WHERE id=:id AND status='SENT'" in w
    assert "reconcile_delivery_reports(cfg,engine)" in w


def test_sms_templates_render_strictly():
    from edusync.modules.communications.domain.models import render_template
    assert render_template("Reçu {{recu}} : {{montant}} {{devise}}", {"recu": "R1", "montant": "10", "devise": "CDF"}) == "Reçu R1 : 10 CDF"
    for body, values in (("{{secret}}", {"secret": "x"}), ("{{recu}}", {}), ("  ", {})):
        with pytest.raises(ValueError):
            render_template(body, values)


# --- finance: family basket / receipts -------------------------------------------------------------------
def test_family_basket_reuses_the_unchanged_collect_rule_atomically():
    repo = (SRC / "adapters/postgres_finance_checkout.py").read_text(encoding="utf-8")
    assert "r=self.collect(school_id,user_id,membership_id,UUID(str(l['enrollment_id']))" in repo
    assert "Idempotency-Key déjà utilisée pour un autre panier" in repo
    assert "Un élève du panier n’appartient pas à cette famille" in repo
    router = (SRC / "modules/finance_checkout/api/router.py").read_text(encoding="utf-8")
    assert "need(actor,'finance.checkout.family.collect');need(actor,'finance.checkout.collect')" in router
    mig = (ROOT / "migrations/0049_finance_family_basket.sql").read_text(encoding="utf-8")
    assert "REVOKE UPDATE, DELETE ON finance_family_baskets, finance_family_basket_payments FROM edusync_tenant" in mig


def test_receipt_pdf_is_generated_outside_the_payment_and_marks_duplicates():
    from datetime import datetime
    from edusync.modules.finance_checkout.application.receipts import money, receipt_pdf
    r = {"receipt_number": "REC-1", "amount": "50000", "currency": "CDF", "created_at": datetime(2026, 10, 6, 9, 0), "cashier": "Caissier",
         "last_name": "MBALA", "first_name": "Jean", "matricule": "M1", "class_label": "6e A", "academic_year": "2026-2027",
         "lines": [{"label": "Minerval · SEPTEMBRE", "amount": "50000"}], "copy_no": 2}
    for fmt in ("A5", "80MM"):
        assert receipt_pdf(school={"name": "École"}, receipts=[r], fmt=fmt).startswith(b"%PDF")
    assert money("50000", "CDF") == "50 000 CDF" and money("12.5", "USD") == "12,50 USD"
    router = (SRC / "modules/finance_checkout/api/router.py").read_text(encoding="utf-8")
    assert "if repo.receipt_copies(actor.school_id,payment_id)>=1:need(actor,'finance.receipts.reprint')" in router


def test_closure_migrations_are_provisioned_in_order():
    prov = (ROOT / "scripts/provision_database.py").read_text(encoding="utf-8")
    names = ["0046_session_lifetime_rotation", "0047_platform_first_manager_setup", "0048_document_object_storage",
             "0049_finance_family_basket", "0050_receipt_printing"]
    positions = [prov.index(f'"{n}.sql"') for n in names]
    assert positions == sorted(positions) and prov.index('"0045_finance_read_model_performance.sql"') < positions[0]
    for n in names:
        assert (ROOT / "migrations" / f"{n}.sql").exists()


# --- frontend shell / UX (static contracts; visual proof in certification/closure-20261006/screens) ------
FRONT = ROOT.parent / "frontend" / "src"


def test_no_emoji_is_used_as_an_interface_icon():
    import re
    pictograph = re.compile("[\U0001F300-\U0001FAFF☀-⛿✀-➿]")
    offenders = {}
    for path in FRONT.rglob("*.tsx"):
        if path.name == "nav_icons.tsx":  # historical glyph keys mapped to SVG, never rendered
            continue
        found = {c for c in pictograph.findall(path.read_text(encoding="utf-8")) if c not in "✓✔"}
        if found:
            offenders[path.name] = sorted(found)
    assert not offenders, offenders


def test_shell_geometry_and_persistence():
    css = (FRONT / "platform/shell.css").read_text(encoding="utf-8")
    shell = (FRONT / "platform/shell.tsx").read_text(encoding="utf-8")
    assert "--es-side:216px" in css and "--es-rail:64px" in css
    assert "localStorage.setItem(COLLAPSED_KEY" in shell and "es-drawer" in shell and "es-bottom" in shell
    assert "@media (max-width:767.98px)" in css  # phone: drawer + bottom bar, not a squeezed desktop sidebar


def test_form_fields_are_explicitly_labelled():
    forms = (FRONT / "platform/forms.tsx").read_text(encoding="utf-8")
    assert "htmlFor={child?id:undefined}" in forms and "'aria-describedby'" in forms and "'aria-invalid'" in forms


def test_sign_in_offers_first_run_setup_only_when_the_server_allows_it():
    login = (FRONT / "login.tsx").read_text(encoding="utf-8")
    assert "setupStatus()" in login and "setup?.setup_required&&setup.setup_available" in login and "createFirstManager(" in login
    assert "Accès Atelier Pro (Manager système)" in login


def test_technical_codes_are_translated_for_users():
    app = (FRONT / "App.tsx").read_text(encoding="utf-8")
    assert "auditActionLabel(x.action)" in app and "resultLabel(x.result)" in app and "schoolStatusLabel(x.status)" in app
    assert "Outbox en attente" not in app and "Verrou global" not in app and "readiness</span>" not in app


def test_fee_tracking_pages_are_stable_and_searchable():
    repo = (SRC / "adapters/postgres_fee_tracking.py").read_text(encoding="utf-8")
    assert "ORDER BY class_label,sort_k1,sort_k2,sort_k3,fee_label,student_id,fee_type_id LIMIT %s OFFSET %s" in repo
    assert ".replace('_'," in repo and "ILIKE %s" in repo and "sum(remaining) OVER()" in repo
    fin = (FRONT / "finance.tsx").read_text(encoding="utf-8")
    assert "const my=++gen.current" in fin and "if(my!==gen.current)return" in fin


def test_unknown_outcome_writes_reuse_their_idempotency_key():
    conn = (FRONT / "platform/connectivity.ts").read_text(encoding="utf-8")
    assert "UNKNOWN_OUTCOME_MS" in conn and "h.set('Idempotency-Key',prev.key)" in conn
    errors = (FRONT / "platform/errors.ts").read_text(encoding="utf-8")
    assert "sera repris dès que possible" not in errors  # no false promise of offline resumption


def test_device_sessions_get_a_readable_label():
    from edusync.shared.infrastructure.persistent_sessions import describe_user_agent
    assert describe_user_agent("Mozilla/5.0 (Windows NT 10.0) AppleWebKit Chrome/140 Safari/537 Edg/145") == "Edge · Windows"
    assert describe_user_agent("Mozilla/5.0 (Linux; Android 14) Chrome/140 Mobile Safari/537") == "Chrome · Android"
    assert describe_user_agent("") == "Navigateur"
