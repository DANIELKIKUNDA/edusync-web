"""Automatic alerts between the school's roles — real HTTP + real PostgreSQL (owner request 2026-11-08).

Proven end to end, with real role assignments (rbac_assignments):
* a cashier cancels a receipt → the gestionnaire is alerted (« Reçu annulé »), the cashier is not;
* a cashier closes the cash desk → the gestionnaire is alerted (closure or counting gap), with a push/e-mail message
  queued in the communications outbox;
* a secondary pupil abandons → the préfet des études (always the secondary) is alerted; the PRIMAIRE section director is not;
* a pending dossier asking for a waiver → those who grant waivers are alerted;
* the recovery follow-up never shows a month twice: a one-time fee (inscription) is its own band, named after the fee.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/alerts_postgres_integration.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, key, one, school, sql  # noqa: E402
from benefits_postgres_integration import child, fees  # noqa: E402


def assign(actor, role: str, school_id, section: str | None = None):
    """A real role assignment, as the access module records it (alerts resolve their audience from it)."""
    rid = one("SELECT id FROM rbac_roles WHERE code=:c AND school_id IS NULL", c=role)[0]
    aid = one("""INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,active,reason)
                 VALUES(:u,:r,:s,:m,true,'test alertes') RETURNING id""", u=actor.user_id, r=rid, s=school_id, m=actor.membership_id)[0]
    sql("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value) VALUES(:a,:t,:v)",
        a=aid, t="SECTION" if section else "SCHOOL", v=section)
    return actor


def inbox(actor, category: str) -> list[str]:
    return [r[0] for r in sql("SELECT title FROM notifications WHERE user_id=:u AND category=:c ORDER BY created_at", u=actor.user_id, c=category).all()]


def run(A: dict) -> None:
    print("\n== Alertes automatiques : caisse, annulations, abandons, dérogations")
    fees(A)
    cls = A["classes"]["PRIMAIRE"]
    gest = assign(actor_for("GESTIONNAIRE", A["id"]), "GESTIONNAIRE", A["id"])
    prefet = assign(actor_for("PREFET_ETUDES", A["id"]), "PREFET_ETUDES", A["id"], section="SECONDAIRE")   # always the secondary
    dir_sec = assign(actor_for("DIRECTION_SECTION", A["id"]), "DIRECTION_SECTION", A["id"], section="PRIMAIRE")
    cashier_actor = assign(actor_for("CAISSIER", A["id"]), "CAISSIER", A["id"])
    clerk = assign(actor_for("CAISSIER", A["id"], drop={"finance.checkout.collect", "finance.checkout.family.collect"}), "CAISSIER", A["id"])

    cashier = as_(cashier_actor)
    o = cashier.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key())
    check("caisse ouverte", o.status_code in (200, 201), o.text[:150])
    guardian = {"full_name": "MBUYI Kalala", "role": "PERE", "phone": "+243 97 000 0011"}
    r = cashier.post("/api/v1/schooling/enrollments/family", headers=key(), json={"household_confidence": "NONE", "primary_guardian": guardian,
                     "children": [child("AL1", cls), child("AL2", cls)], "payment": {"mode": "CASH"}})
    check("inscription avec paiement (2 reçus)", r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    if r.status_code != 201:
        return
    rec = as_(gest).get("/api/v1/finance/recovery/monthly")
    items = rec.json().get("items", []) if rec.status_code == 200 else []
    labels = [i["month_label"] for i in items]
    months = [i for i in items if int(i["ord"]) < 100]
    others = [i for i in items if int(i["ord"]) >= 100]
    check("recouvrement : chaque mois n'apparaît qu'une fois (pas de « Septembre » en double)", rec.status_code == 200 and len(labels) == len(set(labels)), (rec.status_code, labels))
    check("recouvrement : un frais non mensuel a sa propre bande à son nom, jamais un nom de mois",
          bool(others) and all(i["month_label"] not in {m["month_label"] for m in months} for i in others)
          and any("nscription" in i["month_label"] for i in others), labels)
    pil = as_(gest).get("/api/v1/finance/recovery/pilotage")
    paid = one("SELECT COALESCE(sum(amount),0) FROM finance_payments WHERE school_id=:s AND currency='CDF'", s=A["id"])[0]
    check("tableau du promoteur : l'argent du jour = les encaissements réels de la journée",
          pil.status_code == 200 and float(pil.json()["cash"]["CDF"]["today"]) == float(paid) > 0
          and pil.json()["cash"]["CDF"]["today"] == pil.json()["cash"]["CDF"]["year"], (pil.status_code, pil.text[:300], paid))
    as_(cashier_actor)
    pay = one("""SELECT p.id FROM finance_payments p JOIN enrollments e ON e.id=p.enrollment_id JOIN students s ON s.id=e.student_id
                 WHERE s.family_id=:f ORDER BY p.created_at LIMIT 1""", f=r.json()["family_id"])[0]
    v = cashier.post(f"/api/v1/finance/cash/payments/{pay}/reverse", json={"reversal_type": "ANNULATION", "reason": "Erreur de saisie au guichet"})
    check("le caissier annule un reçu", v.status_code == 200, f"{v.status_code} {v.text[:200]}")
    amt = one("SELECT amount FROM finance_payments WHERE id=:i", i=pay)[0]
    after = as_(gest).get("/api/v1/finance/recovery/pilotage").json()["cash"]["CDF"]["today"]
    check("→ l'annulation est déduite de l'argent du jour", float(after) == float(paid) - float(amt), (after, paid, amt))
    # Owner, 2026-11-08: « les montants du caissier et du promoteur ne doivent jamais se contredire »
    pj = as_(gest).get("/api/v1/finance/recovery/pilotage").json()["cash"]["CDF"]
    ses = as_(cashier_actor).get("/api/v1/finance/cash/current").json()["session"]["cdf"]
    day = as_(gest).get("/api/v1/finance/cash/day-summary").json()["currencies"]["CDF"]
    check("un seul caissier : l'argent du jour du promoteur = reçus − annulations de la caisse du caissier",
          float(pj["today"]) == float(ses["receipts"]) - float(ses["reversals"]) == float(pj["today_receipts"]) - float(pj["today_cancellations"]), (pj, ses))
    check("le solde théorique global (promoteur) = le solde théorique de la caisse du caissier",
          float(day["expected_cash"]) == float(ses["expected_cash"]), (day, ses))
    as_(cashier_actor)
    check("→ le gestionnaire reçoit « Reçu annulé » (motif inclus) ; le caissier rien",
          "Reçu annulé" in inbox(gest, "ALERT_FINANCE") and not inbox(cashier_actor, "ALERT_FINANCE"), (inbox(gest, "ALERT_FINANCE"), inbox(cashier_actor, "ALERT_FINANCE")))

    c = cashier.post("/api/v1/finance/cash/close", json={"counted_cdf": "0", "counted_usd": "0"})
    check("le caissier clôture sa caisse", c.status_code == 200, f"{c.status_code} {c.text[:200]}")
    titles = inbox(gest, "ALERT_FINANCE")
    check("→ le gestionnaire est alerté de la clôture (écart au comptage signalé)", any(t in titles for t in ("Caisse clôturée", "Écart à la clôture de caisse")), titles)
    body = one("SELECT body FROM notifications WHERE user_id=:u AND category='ALERT_FINANCE' ORDER BY created_at DESC LIMIT 1", u=gest.user_id)[0]
    check("→ le message est en français et chiffré (montant, reçus, écart)", "a clôturé sa caisse" in body and "reçu" in body, body)
    queued = one("SELECT count(*) FROM communication_messages WHERE school_id=:s AND kind='ALERT'", s=A["id"])[0]
    check("→ notifications push / e-mail mises en file (outbox des communications)", int(queued) >= 2, queued)

    student = one("SELECT s.id,s.version FROM students s WHERE s.id=:i", i=A["pupils"]["SECONDAIRE"])
    a = cashier.post(f"/api/v1/schooling/students/{student[0]}/abandon", headers={**key(), "If-Match": str(student[1])}, json={"reason": "Déménagement à Kolwezi"})
    check("abandon d'un élève du secondaire", a.status_code == 200, f"{a.status_code} {a.text[:200]}")
    check("→ le préfet des études (secondaire) reçoit « Abandon » ; la direction de la section PRIMAIRE ne le reçoit pas",
          "Abandon" in inbox(prefet, "ALERT_ACADEMIC") and not inbox(dir_sec, "ALERT_ACADEMIC"), (inbox(prefet, "ALERT_ACADEMIC"), inbox(dir_sec, "ALERT_ACADEMIC")))

    as_(clerk)
    d = H.CLIENT.post("/api/v1/schooling/enrollment-dossiers", json={"household_confidence": "NONE", "primary_guardian": guardian,
                      "children": [{**child("AL3", cls), "condition_waiver": "Orphelin pris en charge par la paroisse"}]})
    check("dossier en attente avec une demande de dérogation", d.status_code == 201, f"{d.status_code} {d.text[:200]}")
    check("→ ceux qui accordent les dérogations sont alertés (« Dérogation demandée »)", "Dérogation demandée" in inbox(gest, "ALERT_DECISIONS"), inbox(gest, "ALERT_DECISIONS"))


def section_scopes(A: dict) -> None:
    """Owner, 2026-11-08: a section leader sees HIS section only — headcounts and the section's money — never the school."""
    print("\n== Directions de section : effectifs et finances limités à la section")
    seen = {}
    for role, section in (("PREFET_ETUDES", "SECONDAIRE"), ("DIRECTEUR_ETUDES", "SECONDAIRE"), ("DIRECTEUR_DISCIPLINE", "SECONDAIRE"), ("DIRECTION_SECTION", "PRIMAIRE")):
        actor = actor_for(role, A["id"], scope=("SECTION", section))
        r = as_(actor).get("/api/v1/effectifs/counts", params={"group_by": "class"})
        sections = {i["section"] for i in r.json().get("items", [])} if r.status_code == 200 else set()
        seen[role] = sections
        check(f"{role} ({section}) : les effectifs de sa seule section", r.status_code == 200 and len(sections) == 1, (r.status_code, sections, r.text[:200]))
    whole = as_(actor_for("PROMOTEUR", A["id"])).get("/api/v1/effectifs/counts", params={"group_by": "class"}).json()
    check("le promoteur voit toutes les sections, la direction du primaire une autre que le préfet",
          len({i["section"] for i in whole["items"]}) > 1 and seen["DIRECTION_SECTION"] != seen["PREFET_ETUDES"], ({i["section"] for i in whole["items"]}, seen))
    p = as_(actor_for("PREFET_ETUDES", A["id"], scope=("SECTION", "SECONDAIRE"))).get("/api/v1/finance/recovery/pilotage")
    check("préfet : les finances de sa section, jamais l'argent des caisses de l'école", p.status_code == 200 and p.json()["cash"] is None and "recovery" in p.json(), (p.status_code, p.text[:200]))


def main() -> int:
    A = school("F")
    run(A)
    section_scopes(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
