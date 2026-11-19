"""Mois du départ réglé par l'école — real HTTP + real PostgreSQL (owner, 2026-11-19).

« Un enfant qui a abandonné le 15 septembre ne doit pas être compté comme redevable pour ce mois » — « c'est à chaque
école de définir la date ». Checks: the real date of the abandon is kept; the months after it are never owed; the month
of departure follows the school's day (none set → owed; 15 → left on the 15th not owed, left on the 20th owed); a paid
month is never touched; a date in the future is refused; the other settings of the billing policy are preserved.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/departure_month_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import RUN, actor_for, as_, check, key, one, school, sql  # noqa: E402

MONTHS = (("09", "Septembre", 1, "2026-09-01"), ("10", "Octobre", 2, "2026-10-01"), ("11", "Novembre", 3, "2026-11-01"))


def pupil(A: dict, name: str, paid_september: bool = False):
    sid, st, enr, fam = A["id"], uuid.uuid4(), uuid.uuid4(), A["families"]["PRIMAIRE"]
    sql("""INSERT INTO students(id,school_id,family_id,matricule,last_name,middle_name,first_name,gender)
           VALUES(:i,:s,:f,:m,:n,'DEPART','Élève','M')""", i=st, s=sid, f=fam, m=f"DEP-{name}-{RUN}", n=name)
    sql("INSERT INTO enrollments(id,school_id,student_id,academic_year_id,class_id,status,enrolled_on) VALUES(:i,:s,:st,:y,:c,'VALIDATED','2026-09-01')",
        i=enr, s=sid, st=st, y=A["year"], c=A["classes"]["PRIMAIRE"])
    charges = {}
    for code, label, order, due in MONTHS:
        ch = uuid.uuid4(); paid = 20000 if (paid_september and code == "09") else 0
        sql("""INSERT INTO finance_charges(id,school_id,enrollment_id,label,currency,net_amount,paid_amount,periodicity,period_label,period_order,due_date)
               VALUES(:i,:s,:e,:l,'CDF',20000,:p,'MONTHLY',:l,:o,:d)""", i=ch, s=sid, e=enr, l=label, p=paid, o=order, d=due)
        charges[label] = ch
    return st, charges


def status(ch) -> str:
    return one("SELECT status FROM finance_charges WHERE id=:i", i=ch)[0]


def leave(c, st, when: str, kind: str = "abandon"):
    ver = one("SELECT version FROM students WHERE id=:i", i=st)[0]
    body = {"effective_date": when, "reason": "Départ de test"}
    if kind == "transfer":
        body["destination"] = "École voisine"
    return c.post(f"/api/v1/schooling/students/{st}/{kind}", json=body, headers={**key(), "If-Match": str(ver)})


def run(A: dict) -> None:
    print("\n== Mois du départ réglé par l'école (19/11/2026)")
    sid = A["id"]
    # as_() switches the ONE test client to an actor: call admin() / sec() before each request of that actor.
    a_admin = actor_for("GESTIONNAIRE", sid, extra={"settings.billing_months.manage", "settings.tariffs.read"})
    admin = lambda: as_(a_admin)  # noqa: E731
    r = admin().put("/api/v1/settings/billing-policy", json={"billing_months": ["09", "10", "11", "12", "01", "02", "03", "04", "05", "06"],
                                                          "month_due_at_enrollment": "06"}, headers=key())
    check("politique de facturation sans règle de départ", r.status_code == 200 and r.json().get("departure_month_not_due_until_day") is None, r.text[:200])
    a_sec = actor_for("SECRETARIAT", sid, extra={"students.lifecycle.abandon", "students.lifecycle.transfer"})
    sec = lambda: as_(a_sec)  # noqa: E731

    st, ch = pupil(A, "SANSREGLE")
    r = leave(sec(), st, "2026-09-15")
    check("abandon le 15/09 enregistré à sa vraie date", r.status_code == 200
          and str(one("SELECT effective_date FROM student_status_events WHERE student_id=:s", s=st)[0]) == "2026-09-15", r.text[:200])
    check("sans règle : septembre reste dû, octobre et novembre ne le sont plus",
          (status(ch["Septembre"]), status(ch["Octobre"]), status(ch["Novembre"])) == ("ACTIVE", "CANCELLED", "CANCELLED"),
          [status(x) for x in ch.values()])

    pol = admin().get("/api/v1/settings/billing-policy").json()
    r = admin().put("/api/v1/settings/billing-policy", json={"billing_months": pol["billing_months"], "month_due_at_enrollment": pol["month_due_at_enrollment"],
                                                          "departure_month_not_due_until_day": 15, "expected_version": pol["version"]}, headers=key())
    check("l'école règle : parti jusqu'au 15 → mois non dû", r.status_code == 200 and r.json()["departure_month_not_due_until_day"] == 15, r.text[:200])
    pol = admin().get("/api/v1/settings/billing-policy").json()
    r = admin().put("/api/v1/settings/billing-policy", json={"billing_months": pol["billing_months"], "month_due_at_enrollment": "06",
                                                          "expected_version": pol["version"]}, headers=key())
    check("un ancien écran qui n'envoie pas la règle ne l'efface pas", r.status_code == 200 and r.json()["departure_month_not_due_until_day"] == 15, r.text[:200])

    st, ch = pupil(A, "QUINZE")
    leave(sec(), st, "2026-09-15")
    check("règle 15, abandon le 15/09 : septembre n'est plus dû", status(ch["Septembre"]) == "CANCELLED" and status(ch["Octobre"]) == "CANCELLED",
          [status(x) for x in ch.values()])
    st, ch = pupil(A, "VINGT")
    leave(sec(), st, "2026-09-20", "transfer")
    check("règle 15, transfert le 20/09 : septembre reste dû, octobre non", (status(ch["Septembre"]), status(ch["Octobre"])) == ("ACTIVE", "CANCELLED"),
          [status(x) for x in ch.values()])
    st, ch = pupil(A, "PAYE", paid_september=True)
    leave(sec(), st, "2026-09-10")
    check("un mois déjà payé n'est jamais annulé", status(ch["Septembre"]) == "ACTIVE" and status(ch["Octobre"]) == "CANCELLED",
          [status(x) for x in ch.values()])
    st, _ = pupil(A, "FUTUR")
    r = leave(sec(), st, "2099-01-01")
    check("date d'abandon dans le futur refusée", r.status_code in (400, 409, 422), r.status_code)


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
