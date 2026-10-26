"""Real disposable PostgreSQL integration for cashier receipt and official report invariants.

Run only against the CI PostgreSQL service after provision_database.py. No staging endpoint.
"""
from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from uuid import uuid4

from sqlalchemy import create_engine, text

from edusync.adapters.postgres_periodic_reports import PostgresPeriodicReportsRepository
from edusync.modules.documents.application.object_store import (
    archive_official_pdf_strict,
    configure_storage,
    read_official_pdf,
)
from edusync.shared.infrastructure.object_storage import LocalObjectStorage, ObjectStorageError


owner_url = os.environ["EDUSYNC_OWNER_DATABASE_URL"]
tenant_url = os.environ["EDUSYNC_TENANT_DATABASE_URL"]
assert os.environ.get("CI") == "true", "CI jetable uniquement"
assert "127.0.0.1" in owner_url and "127.0.0.1" in tenant_url, "Base distante refusée"
owner = create_engine(owner_url, future=True)
tenant = create_engine(tenant_url, future=True)
school, other, user, membership = (uuid4() for _ in range(4))
year, section, klass, family, student, enrollment, cash = (uuid4() for _ in range(7))
payment, rolled_back_payment = uuid4(), uuid4()
report_key, failed_key = f"cashier-ci-{uuid4().hex}", f"cashier-ci-fail-{uuid4().hex}"
actor = SimpleNamespace(school_id=school, user_id=user)


def scope(conn, sid):
    for key in ("app.school_id", "app.current_school_id"):
        conn.execute(text("SELECT set_config(:key,:sid,true)"), {"key": key, "sid": str(sid)})


try:
    with owner.begin() as c:
        scope(c, school)
        c.execute(text("INSERT INTO schools(id,code,name) VALUES(:id,:code,'Cashier CI')"),
                  {"id": school, "code": f"CI-{school.hex[:12]}"})
        c.execute(text("INSERT INTO users(id,email,full_name,password_hash) VALUES(:id,:email,'Cashier CI','unused-ci-hash')"),
                  {"id": user, "email": f"cashier-{user.hex}@example.invalid"})
        c.execute(text("INSERT INTO school_memberships(id,school_id,user_id) VALUES(:id,:s,:u)"),
                  {"id": membership, "s": school, "u": user})
        c.execute(text("INSERT INTO academic_years(id,school_id,code,label,start_date,end_date,status) VALUES(:id,:s,'CI-2026','CI 2026','2026-01-01','2026-12-31','ACTIVE')"),
                  {"id": year, "s": school})
        c.execute(text("INSERT INTO school_sections(id,school_id,code,label) VALUES(:id,:s,'GEN','Général')"),
                  {"id": section, "s": school})
        c.execute(text("INSERT INTO school_classes(id,school_id,academic_year_id,section_id,code,label) VALUES(:id,:s,:y,:section,'CI-1','Classe CI')"),
                  {"id": klass, "s": school, "y": year, "section": section})
        c.execute(text("INSERT INTO families(id,school_id,code,display_name) VALUES(:id,:s,'CI-F','Famille CI')"),
                  {"id": family, "s": school})
        c.execute(text("INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name) VALUES(:id,:s,:f,'CI-001','TEST','CAISSIER','ÉLÈVE')"),
                  {"id": student, "s": school, "f": family})
        c.execute(text("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id) VALUES(:id,:s,:st,:y,:class)"),
                  {"id": enrollment, "s": school, "st": student, "y": year, "class": klass})
        c.execute(text("INSERT INTO finance_cash_sessions(id,school_id,membership_id) VALUES(:id,:s,:m)"),
                  {"id": cash, "s": school, "m": membership})
        payment_sql = text("""INSERT INTO finance_payments(id,school_id,enrollment_id,cash_session_id,actor_user_id,amount,currency,receipt_number,idempotency_key)
                    VALUES(:id,:s,:e,:cash,:u,50000,'CDF',:receipt,:key)""")
        c.execute(payment_sql, {"id": payment, "s": school, "e": enrollment, "cash": cash,
                                "u": user, "receipt": f"CI-{payment.hex[:12]}", "key": f"CI-{payment.hex}"})
        assert c.execute(text("SELECT status FROM finance_receipt_print_jobs WHERE payment_id=:p"),
                         {"p": payment}).scalar_one() == "PENDING"
        nested = c.begin_nested()
        c.execute(payment_sql, {"id": rolled_back_payment, "s": school, "e": enrollment, "cash": cash,
                                "u": user, "receipt": f"CI-{rolled_back_payment.hex[:12]}", "key": f"CI-{rolled_back_payment.hex}"})
        assert c.execute(text("SELECT count(*) FROM finance_receipt_print_jobs WHERE payment_id=:p"),
                         {"p": rolled_back_payment}).scalar_one() == 1
        nested.rollback()
        assert c.execute(text("SELECT count(*) FROM finance_receipt_print_jobs WHERE payment_id=:p"),
                         {"p": rolled_back_payment}).scalar_one() == 0

    with tenant.begin() as c:
        scope(c, school)
        assert c.execute(text("SELECT count(*) FROM finance_receipt_print_jobs WHERE payment_id=:p"),
                         {"p": payment}).scalar_one() == 1
    with tenant.begin() as c:
        scope(c, other)
        assert c.execute(text("SELECT count(*) FROM finance_receipt_print_jobs WHERE payment_id=:p"),
                         {"p": payment}).scalar_one() == 0

    with TemporaryDirectory(prefix="edusync-cashier-ci-") as directory:
        storage = LocalObjectStorage(Path(directory))
        storage.ensure_bucket()
        configure_storage(storage)
        with tenant.begin() as c:
            scope(c, school)
            repo = PostgresPeriodicReportsRepository(c)
            issued = repo.register(school, user_id=user, profile_code="CONSOLIDE", period_type="JOURNALIER",
                                   start_date=date(2026, 10, 26), end_date=date(2026, 10, 26),
                                   report={"partial_reporting_mode": "SEPARATE", "totals": {}}, request_key=report_key)
            gen_id, object_key = archive_official_pdf_strict(c, actor, data=b"%PDF-1.4\nCI report\n",
                document_code="finance.reports.periodic.CONSOLIDE", title="Rapport CI",
                file_name=f"rapport_{issued['label']}.pdf", required_capability="finance.reports.periodic.generate")
            c.execute(text("UPDATE finance_generated_reports SET document_generation_id=:g WHERE id=:id AND school_id=:s"),
                      {"g": gen_id, "id": issued["id"], "s": school})
        assert read_official_pdf(object_key, school) == b"%PDF-1.4\nCI report\n"
        with tenant.begin() as c:
            scope(c, school)
            row = c.execute(text("SELECT r.report_label,r.document_generation_id,g.object_key FROM finance_generated_reports r JOIN generated_documents g ON g.id=r.document_generation_id WHERE r.school_id=:s AND r.request_key=:key"),
                            {"s": school, "key": report_key}).mappings().one()
            assert row["report_label"] == issued["label"] and str(row["document_generation_id"]) == gen_id
            assert row["object_key"] == object_key
        previous_number = issued["number"]
        configure_storage(None)
        try:
            with tenant.begin() as c:
                scope(c, school)
                failed = PostgresPeriodicReportsRepository(c).register(
                    school, user_id=user, profile_code="CONSOLIDE", period_type="JOURNALIER",
                    start_date=date(2026, 10, 26), end_date=date(2026, 10, 26),
                    report={"partial_reporting_mode": "SEPARATE", "totals": {}}, request_key=failed_key)
                archive_official_pdf_strict(c, actor, data=b"%PDF-fail", document_code="finance.reports.periodic.CONSOLIDE",
                    title="Rapport CI échec", file_name=f"rapport_{failed['label']}.pdf",
                    required_capability="finance.reports.periodic.generate")
        except ObjectStorageError:
            pass
        else:
            raise AssertionError("Un archivage indisponible doit annuler la transaction")
        with tenant.begin() as c:
            scope(c, school)
            assert c.execute(text("SELECT count(*) FROM finance_generated_reports WHERE school_id=:s AND request_key=:key"),
                             {"s": school, "key": failed_key}).scalar_one() == 0
            assert c.execute(text("SELECT last_number FROM finance_report_sequences WHERE school_id=:s AND academic_year_id=:y"),
                             {"s": school, "y": year}).scalar_one() == previous_number
finally:
    configure_storage(None)
    owner.dispose()
    tenant.dispose()

print("CASHIER_POSTGRES_INTEGRATION=PASS")
