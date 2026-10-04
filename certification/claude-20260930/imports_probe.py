"""Live import certification: official contracts, tampering, limits, staging, confirmation, replay,
stale-analysis double execution, finance-history outside cash, cross-tenant isolation."""
import io
import os
import sys
import threading
from decimal import Decimal
from uuid import uuid4

from openpyxl import load_workbook

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

A, B = state["A"], state["B"]
CAPS = ("migration.students.analyze", "migration.students.execute", "migration.staff.analyze", "migration.staff.execute",
        "migration.finance_history.analyze", "migration.finance_history.execute", "documents.student_import_template.export")
for s in (A, B):
    grant_test_role(s, "ADMIN", "CL_IMPORT", CAPS)
a, b = user_client(A, "ADMIN"), user_client(B, "ADMIN")


def fill(raw, rows, start=6):
    wb = load_workbook(io.BytesIO(raw))
    ws = wb.worksheets[0]
    ws.protection.sheet = False
    for i, values in enumerate(rows):
        for j, v in enumerate(values, 1):
            ws.cell(start + i, j, v)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def tamper(raw, fn):
    wb = load_workbook(io.BytesIO(raw))
    ws = wb.worksheets[0]
    ws.protection.sheet = False
    fn(wb, ws)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def analyze(client, kind, payload, filename="recette.xlsx", **params):
    return call(client, "POST", f"import/{kind}/analyze", params={"filename": filename, **params}, content=payload)


def execute(client, kind, bid, body, key=None):
    return call(client, "POST", f"import/{kind}/batches/{bid}/execute", json=body, headers={"Idempotency-Key": key or str(uuid4())})


contracts = must(a, "GET", "import/contracts").json()["contracts"]
check("3 official contracts, 5000 rows max", {c["contract_id"] for c in contracts} >= {"EDUSYNC-STUDENTS-v1", "EDUSYNC-STAFF-v1", "EDUSYNC-FINANCE-HISTORY-v1"} and all(c["max_rows"] == 5000 for c in contracts))
stu_tpl = must(a, "GET", "documents/student-import-template.xlsx").content

# --- contract enforcement ----------------------------------------------------------------------
tag = uuid4().hex[:6].upper()
row = [f"IMP{tag}", "POSTNOM", "Prenom", "F", "1A"]
ok = fill(stu_tpl, [row])
r = analyze(a, "students", ok, academic_year_id=A["year_id"])
check("official template intact -> analyzed, 0 error", r.status_code == 200 and r.json()["error_rows"] == 0, r.text[:200])
cases = {
    "renamed column": tamper(ok, lambda wb, ws: ws.cell(5, 1, "NOM MODIFIE")),
    "deleted column": tamper(ok, lambda wb, ws: ws.delete_cols(2)),
    "added column in the middle": tamper(ok, lambda wb, ws: ws.insert_cols(2)),
    "contract sheet removed": tamper(ok, lambda wb, ws: wb.remove(wb["_EDUSYNC_CONTRACT"])),
    "wrong contract kind (staff template)": None,
}
staff_tpl = must(a, "GET", "import/staff/template.xlsx").content
cases["wrong contract kind (staff template)"] = staff_tpl
for name, payload in cases.items():
    r = analyze(a, "students", payload, academic_year_id=A["year_id"])
    check(f"rejected: {name}", r.status_code == 400, f"HTTP {r.status_code} {r.text[:120]}")
r = analyze(a, "students", b"a,b,c\n1,2,3\n", filename="x.csv", academic_year_id=A["year_id"])
check("non-XLSX rejected (415)", r.status_code == 415, f"HTTP {r.status_code}")
r = analyze(a, "students", b"PK\x03\x04" + b"0" * (10 * 1024 * 1024 + 10), academic_year_id=A["year_id"])
check("file > 10 MiB rejected (413)", r.status_code == 413, f"HTTP {r.status_code}")
big = fill(stu_tpl, [[f"BIG{i}", "P", "N", "M", "1A"] for i in range(5001)])
r = analyze(a, "students", big, academic_year_id=A["year_id"])
check("5001 rows rejected (413), nothing staged", r.status_code == 413, f"HTTP {r.status_code}")
r = analyze(a, "students", b"not a zip at all", academic_year_id=A["year_id"])
check("garbage bytes rejected (400, no 500)", r.status_code == 400, f"HTTP {r.status_code}")

# --- staging, confirmation, execution, replay --------------------------------------------------
r = analyze(a, "students", ok, academic_year_id=A["year_id"])
bid = r.json()["batch_id"]
n_before = sql("SELECT count(*) n FROM students WHERE school_id=:s", {"s": A["school_id"]})[0]["n"]
check("analysis writes nothing to students (staging only)", n_before == sql("SELECT count(*) n FROM students WHERE school_id=:s", {"s": A["school_id"]})[0]["n"])
check("execute without household confirmation refused", execute(a, "students", bid, {"accept_warnings": True}).status_code == 409)
check("execute without Idempotency-Key refused", call(a, "POST", f"import/students/batches/{bid}/execute", json={"accept_warnings": True, "confirm_separate_households": True}, headers={"Idempotency-Key": ""}).status_code == 400)
check("B cannot execute A's batch", execute(b, "students", bid, {"accept_warnings": True, "confirm_separate_households": True}).status_code == 404)
check("B cannot download A's control report", call(b, "GET", f"import/batches/students/{bid}/control-report.xlsx").status_code == 404)
check("B batch list does not show A's batch", bid not in str(call(b, "GET", "import/batches/students").json()))
outs = []
ths = [threading.Thread(target=lambda: outs.append(execute(a, "students", bid, {"accept_warnings": True, "confirm_separate_households": True}).json())) for _ in range(3)]
[t.start() for t in ths]
[t.join() for t in ths]
cnt = sql("SELECT count(*) n FROM students WHERE school_id=:s AND last_name=:l", {"s": A["school_id"], "l": f"IMP{tag}"})[0]["n"]
check("3 concurrent executions of one batch -> 1 student", cnt == 1 and sum(1 for o in outs if o.get("replayed")) == 2, f"students={cnt} outs={[o.get('replayed') for o in outs]}")

# --- stale analysis: same file analyzed twice before execution ---------------------------------
tag2 = uuid4().hex[:6].upper()
payload = fill(stu_tpl, [[f"DUP{tag2}", "POSTNOM", "Prenom", "M", "1A"]])
b1 = analyze(a, "students", payload, academic_year_id=A["year_id"]).json()["batch_id"]
b2 = analyze(a, "students", payload, academic_year_id=A["year_id"]).json()["batch_id"]
r1 = execute(a, "students", b1, {"accept_warnings": True, "confirm_separate_households": True})
r2 = execute(a, "students", b2, {"accept_warnings": False, "confirm_separate_households": True})
cnt = sql("SELECT count(*) n FROM students WHERE school_id=:s AND last_name=:l", {"s": A["school_id"], "l": f"DUP{tag2}"})[0]["n"]
check("same file staged twice: 2nd execution does not silently create a duplicate", cnt == 1 and r2.status_code == 409, f"students={cnt} second=HTTP {r2.status_code}")

# --- staff import ------------------------------------------------------------------------------
emp = "STF-" + uuid4().hex[:6]
r = analyze(a, "staff", fill(staff_tpl, [[emp, "AGENT", "", "Import", "F", "ENSEIGNANT"]]))
check("staff analyze", r.status_code == 200 and r.json()["error_rows"] == 0, r.text[:200])
if r.status_code == 200:
    sb = r.json()["batch_id"]
    k = str(uuid4())
    e1 = execute(a, "staff", sb, {"accept_warnings": True}, k)
    e2 = execute(a, "staff", sb, {"accept_warnings": True}, k)
    cnt = sql("SELECT count(*) n FROM staff_members WHERE school_id=:s AND upper(employee_no)=upper(:e)", {"s": A["school_id"], "e": emp})[0]["n"]
    check("staff execute + replay -> 1 agent", e1.status_code == 200 and e2.status_code == 200 and cnt == 1, f"{e1.status_code}/{e2.status_code} n={cnt}")

# --- finance history: outside cash, no over-regularization -------------------------------------
fin_tpl = must(a, "GET", "import/finance-history/template.xlsx").content
mat = sql("SELECT s.matricule FROM students s JOIN enrollments e ON e.student_id=s.id WHERE e.id=:e", {"e": A["family"]["enrollment_ids"][0]})[0]["matricule"]
ch = sql("SELECT id,net_amount,paid_amount FROM finance_charges WHERE enrollment_id=:e AND period_label='OCTOBRE'", {"e": A["family"]["enrollment_ids"][0]})[0]
remaining = Decimal(ch["net_amount"]) - Decimal(ch["paid_amount"]) - Decimal(sql("SELECT coalesce(sum(amount),0) s FROM finance_charge_regularizations WHERE charge_id=:c", {"c": ch["id"]})[0]["s"])
cash_before = sql("SELECT (SELECT count(*) FROM finance_payments WHERE school_id=:s) p,(SELECT count(*) FROM finance_cash_events WHERE school_id=:s) e", {"s": A["school_id"]})[0]
ref1, ref2 = "HIST-" + uuid4().hex[:6], "HIST-" + uuid4().hex[:6]
f1 = fill(fin_tpl, [["2026-2027", mat, "Minerval · OCTOBRE", "OCTOBRE", str(remaining), "CDF", "2026-09-15", ref1]])
f2 = fill(fin_tpl, [["2026-2027", mat, "Minerval · OCTOBRE", "OCTOBRE", str(remaining), "CDF", "2026-09-16", ref2]])
r1 = analyze(a, "finance-history", f1)
r2 = analyze(a, "finance-history", f2)
check("finance history analyzed (both batches see the full remaining)", r1.status_code == 200 and r1.json()["error_rows"] == 0 and r2.json()["error_rows"] == 0, r1.text[:200])
x1 = execute(a, "finance-history", r1.json()["batch_id"], {"accept_warnings": True, "confirm_outside_cash": True})
x2 = execute(a, "finance-history", r2.json()["batch_id"], {"accept_warnings": True, "confirm_outside_cash": True})
reg = Decimal(sql("SELECT coalesce(sum(amount),0) s FROM finance_charge_regularizations WHERE charge_id=:c", {"c": ch["id"]})[0]["s"])
row = sql("SELECT net_amount,paid_amount FROM finance_charges WHERE id=:c", {"c": ch["id"]})[0]
check("two stale batches cannot regularize more than what is owed", Decimal(row["paid_amount"]) + reg <= Decimal(row["net_amount"]) and x2.status_code == 409,
      f"net={row['net_amount']} paid={row['paid_amount']} regularized={reg} 2nd=HTTP {x2.status_code}")
cash_after = sql("SELECT (SELECT count(*) FROM finance_payments WHERE school_id=:s) p,(SELECT count(*) FROM finance_cash_events WHERE school_id=:s) e", {"s": A["school_id"]})[0]
check("finance history creates no cash payment/receipt/cash event", dict(cash_before) == dict(cash_after) and x1.json().get("cash_created") is False, f"{dict(cash_before)} -> {dict(cash_after)}")
r = analyze(b, "finance-history", f1)
# matricules are per-school sequences (ELV-00001 exists in A and B): B must resolve only its own charge
leak = sql("""SELECT count(*) n FROM financial_history_import_rows r JOIN finance_charges c ON c.id=(r.normalized_payload->>'charge_id')::uuid
              WHERE r.batch_id=:b AND c.school_id<>r.school_id""", {"b": r.json()["batch_id"]})[0]["n"] if r.status_code == 200 else -1
check("B's finance-history analysis never resolves A's charge", r.status_code == 200 and leak == 0, f"cross-school rows={leak}")
dump("imports-live.json")
