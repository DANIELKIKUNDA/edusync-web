"""Envoi du rapport aux responsables — real HTTP + real PostgreSQL (owner, 2026-11-19).

Real members with real role assignments: a promoteur (whole school), a préfet limited to the Secondaire and a cashier.
« Envoyer le mois » gives one e-mail with ITS PDF to the promoteur and to the préfet, none to the cashier; « Envoyer la
semaine » only to the promoteur; sending again sends nothing twice; only a whole-school supervisor may send.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/digest_send_postgres_integration.py

CI=true, localhost only (three_roles_postgres_integration). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, key, one, school, sql  # noqa: E402
import direction_report_postgres_integration as D  # noqa: E402

B = "/api/v1/finance/recovery/digest/send"


def member(sid, role: str, name: str, scope: tuple | None = None) -> uuid.UUID:
    uid, mid, aid = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    sql("INSERT INTO users(id,email,full_name,password_hash,active,version) VALUES(:i,:e,:n,'x',true,1)", i=uid, e=f"{name.lower()}-{uid.hex[:6]}@example.test", n=name)
    sql("INSERT INTO school_memberships(id,school_id,user_id,active,version) VALUES(:i,:s,:u,true,1)", i=mid, s=sid, u=uid)
    rid = one("SELECT id FROM rbac_roles WHERE code=:c AND kind='SCHOOL_STANDARD' AND school_id IS NULL", c=role)[0]
    sql("INSERT INTO rbac_assignments(id,user_id,role_id,school_id,membership_id,active) VALUES(:i,:u,:r,:s,:m,true)", i=aid, u=uid, r=rid, s=sid, m=mid)
    sql("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,:t,:v)", a=aid, t=(scope or ("SCHOOL", None))[0], v=(scope or ("SCHOOL", None))[1])
    return uid


def reports(sid) -> list:
    return [tuple(r) for r in sql("""SELECT r.user_id, a.byte_size, substring(a.data from 1 for 4) FROM communication_messages m
        JOIN communication_recipients r ON r.message_id=m.id JOIN communication_attachments a ON a.message_id=m.id
        WHERE m.school_id=:s AND m.kind='REPORT'""", s=sid).all()]


def run(A: dict) -> None:
    print("\n== Envoi du rapport aux responsables (19/11/2026)")
    D.fixture(A)
    sid = A["id"]
    prom = member(sid, "PROMOTEUR", "Promoteur")
    pref = member(sid, "PREFET_ETUDES", "Prefet", ("SECTION", "SECONDAIRE"))
    cais = member(sid, "CAISSIER", "Caissier")
    sender = lambda: as_(actor_for("PROMOTEUR", sid))  # noqa: E731
    r = sender().post(B, json={"kind": "MONTH"}, headers=key())
    check("envoi du mois accepté", r.status_code == 200, r.text[:300])
    got = reports(sid); users = {str(x[0]) for x in got}
    check("promoteur et préfet reçoivent leur rapport, pas le caissier", users == {str(prom), str(pref)}, got)
    check("chaque e-mail porte un vrai PDF", all(bytes(x[2]) == b"%PDF" and x[1] > 1000 for x in got), [(x[1], bytes(x[2])) for x in got])
    r = sender().post(B, json={"kind": "MONTH"}, headers=key())
    check("renvoyer le même mois n'envoie rien deux fois", r.status_code == 200 and not r.json()["sent"] and len(r.json()["already_sent"]) == 2
          and len(reports(sid)) == 2, r.text[:300])
    before = len(reports(sid))
    r = sender().post(B, json={"kind": "WEEK"}, headers=key())
    new = len(reports(sid)) - before
    check("la semaine ne part qu'aux responsables de toute l'école", r.status_code == 200 and new == 1 and len(r.json()["sent"]) == 1, (new, r.text[:300]))
    p = as_(actor_for("PREFET_ETUDES", sid, scope=("SECTION", "SECONDAIRE"), extra={"finance.cash.other.read"})).post(B, json={"kind": "MONTH"}, headers=key())
    check("un préfet ne peut pas envoyer pour toute l'école", p.status_code == 403, p.status_code)
    c = as_(actor_for("CAISSIER", sid)).post(B, json={"kind": "MONTH"}, headers=key())
    check("un caissier ne peut pas envoyer", c.status_code == 403, c.status_code)
    _ = cais


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
