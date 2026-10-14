"""Live probe — parity lot L1: tariff rules copied from the Desktop golden master.

Desktop reference (EduSync École Offline 0.11.0-rc.1, app/db/configuration.py): upsert_tariff_rule, save_tariff_group_rule,
set_option_tariff_group, resolve_tariff_for_class (class 600 > academic class 500 > Humanities group 350 > section 200 >
school 100, at a date), save_monthly_billing_policy, prepare_year_from_previous (ACTIVE -> PENDING_OFFICIAL, shifted dates).
Runs on a fresh school created through the platform API (no shared fixture is modified).
"""
import json
import sys
from pathlib import Path
from uuid import uuid4

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import ensure_user, grant_test_role, owner, platform, save, state, user_client  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def k(extra=None):
    return {"Idempotency-Key": str(uuid4()), **(extra or {})}


run = uuid4().hex[:5].upper()
mgr = platform()
s = mgr.post("platform/schools", json={"code": f"L1-{run}", "name": f"École tarifs L1 {run}"}, headers=k())
assert s.status_code == 201, s.text[:200]
school = {"code": f"L1-{run}", "school_id": s.json()["id"], "users": {}}
state.setdefault("L1", {})[run] = school
save()
ensure_user(school, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
adm = user_client(school, "ADMIN")


def ok(r, codes=(200, 201)):
    assert r.status_code in codes, (r.request.method, str(r.request.url)[-60:], r.status_code, r.text[:300])
    return r.json()


y = ok(adm.post("settings/academic-years", json={"code": "2026-2027", "label": "2026-2027", "start_date": "2026-09-01", "end_date": "2027-06-30"}, headers=k()))
y = ok(adm.post(f"settings/academic-years/{y['id']}/activate", headers=k({"If-Match": str(y["version"])})))
sec = ok(adm.put("settings/sections/SECONDAIRE", json={"code": "SECONDAIRE", "label": "Secondaire", "enabled": True}, headers=k()))
pri = ok(adm.put("settings/sections/PRIMAIRE", json={"code": "PRIMAIRE", "label": "Primaire", "enabled": True}, headers=k()))
com = ok(adm.put("settings/options/COMMERCIALE", json={"section_id": sec["id"], "code": "COMMERCIALE", "label": "Commerciale", "tariff_group_code": "GENERAL"}, headers=k()))
mec = ok(adm.put("settings/options/MECANIQUE", json={"section_id": sec["id"], "code": "MECANIQUE", "label": "Mécanique", "tariff_group_code": "TECHNICAL"}, headers=k()))


def cls(code, ref, section, option=None):
    return ok(adm.post("settings/classes", json={"academic_year_id": y["id"], "section_id": section["id"], "reference_code": ref, "code": code,
                                                 "label": code, "option_id": option["id"] if option else None}, headers=k()))


h1c, h1m, h2c, s7, p1 = cls("H1COM", "H1", sec, com), cls("H1MEC", "H1", sec, mec), cls("H2COM", "H2", sec, com), cls("S7A", "S7", sec), cls("P1A", "P1", pri)
fee = ok(adm.post("settings/fee-types", json={"code": "MINERVAL", "label": "Minerval", "periodicity": "MONTHLY", "default_currency": "CDF"}, headers=k()))


def rule(scope, ref, amount, status="ACTIVE", eff=None, client=None, source=None):
    body = {"academic_year_id": y["id"], "fee_type_id": fee["id"], "scope_type": scope, "scope_ref": ref, "amount": amount, "currency": "CDF",
            "status": status, "effective_from": eff, "source_reference": source}
    return (client or adm).put("settings/tariff-rules", json=body, headers=k())


def resolved(c, as_of=None):
    r = adm.get("settings/tariffs/resolve", params={"class_id": c["id"], "fee_type_id": fee["id"], **({"as_of": as_of} if as_of else {})})
    return r.json() if r.status_code == 200 else {"error": r.status_code}


for scope, ref, amount in (("SCHOOL", None, "10000"), ("SECTION", sec["id"], "20000"), ("OPTION_GROUP", "GENERAL", "30000"),
                           ("ACADEMIC_CLASS", "H1", "40000"), ("CLASS", h1c["id"], "50000")):
    r = rule(scope, ref, amount)
    check(f"Règle {scope} enregistrée", r.status_code == 201, r.status_code)

expect = {"H1COM classe": (h1c, "50000.00", "CLASS"), "H1MEC classe académique (groupe technique sans règle)": (h1m, "40000.00", "ACADEMIC_CLASS"),
          "H2COM groupe Humanités générales": (h2c, "30000.00", "OPTION_GROUP"), "S7A section": (s7, "20000.00", "SECTION"), "P1A école": (p1, "10000.00", "SCHOOL")}
for name, (c, amount, scope) in expect.items():
    got = resolved(c)
    check(f"Résolution {name} : {amount} ({scope})", got.get("amount") == amount and got.get("scope_type") == scope, (got.get("amount"), got.get("scope_type")))

# ---------- effective dates ----------
r = rule("CLASS", h1c["id"], "60000", eff="2027-02-01")
check("Nouvelle règle datée de février (même classe)", r.status_code == 201, r.status_code)
check("Avant février : l'ancien montant s'applique", resolved(h1c, "2026-12-01").get("amount") == "50000.00")
check("Dès février : le nouveau montant s'applique", resolved(h1c, "2027-03-01").get("amount") == "60000.00")
r = rule("CLASS", h1c["id"], "61000", eff="2027-02-01", source="Correction")
check("Même cible et même date : la règle est mise à jour (pas de doublon)", r.status_code == 200 and r.json().get("amount") == "61000.00", r.status_code)
r = rule("CLASS", h1c["id"], "70000", eff="2027-08-15")
check("Date d'effet hors de l'année refusée", r.status_code in (409, 422), r.status_code)

# ---------- status and amounts ----------
r = rule("CLASS", h2c["id"], None, status="PENDING_OFFICIAL", source="Barème de l'État attendu")
got = resolved(h2c)
check("Barème officiel en attente : la règle la plus précise reste en attente (pas de repli sur le groupe)",
      r.status_code == 201 and got.get("status") == "PENDING_OFFICIAL" and got.get("amount") is None, (r.status_code, got.get("status")))
check("Tarif actif sans montant refusé", rule("CLASS", s7["id"], None).status_code in (409, 422))
check("Montant négatif refusé", rule("CLASS", s7["id"], "-5").status_code == 422)
r = rule("CLASS", p1["id"], "0")
check("Montant zéro accepté (règle plus précise qui exonère la classe)", r.status_code == 201 and resolved(p1).get("amount") == "0.00", r.status_code)
check("Groupe tarifaire inconnu refusé", rule("OPTION_GROUP", "SCIENCES", "1").status_code in (409, 422))

# ---------- capabilities ----------
ensure_user(school, "TARIF", ())
grant_test_role(school, "TARIF", "RECETTE_TARIFS", ("settings.tariffs.read", "settings.tariffs.manage", "settings.structure.read", "settings.options.manage"))
tc = user_client(school, "TARIF")
check("Sans « barèmes de groupe » : règle de groupe refusée (403)", rule("OPTION_GROUP", "TECHNICAL", "35000", client=tc).status_code == 403)
check("Avec « tarifs » : règle de classe acceptée", rule("CLASS", s7["id"], "21000", client=tc).status_code == 201)
r = tc.put("settings/options/MECANIQUE", json={"section_id": sec["id"], "code": "MECANIQUE", "label": "Mécanique", "tariff_group_code": "GENERAL", "expected_version": mec["version"]}, headers=k())
check("Sans « groupes tarifaires d'options » : changement de groupe refusé (403)", r.status_code == 403, r.status_code)
r = tc.put("settings/options/MECANIQUE", json={"section_id": sec["id"], "code": "MECANIQUE", "label": "Mécanique (renommée)", "expected_version": mec["version"]}, headers=k())
opts = {o["code"]: o for o in adm.get("settings/options").json()}
check("Mise à jour d'une option sans envoyer le groupe : le groupe est conservé", r.status_code == 200 and opts["MECANIQUE"]["tariff_group_code"] == "TECHNICAL", (r.status_code, opts["MECANIQUE"]["tariff_group_code"]))
r = tc.put("settings/tariff-rules", json={"academic_year_id": y["id"], "fee_type_id": fee["id"], "scope_type": "SECTION", "scope_ref": sec["id"], "amount": "1", "currency": "CDF"}, headers=k())
check("Droit « tarifs » : modification de la règle de section acceptée", r.status_code == 200, r.status_code)

# ---------- monthly billing policy ----------
bp = adm.get("settings/billing-policy").json()
check("Mois de facturation par défaut (Desktop) : septembre à juin", bp.get("billing_months") == ["09", "10", "11", "12", "01", "02", "03", "04", "05", "06"], bp)
r = adm.put("settings/billing-policy", json={"billing_months": ["09", "10"], "month_due_at_enrollment": "06", "expected_version": bp.get("version")}, headers=k())
check("Mois exigé à l'inscription hors des mois facturés : refusé", r.status_code in (409, 422), r.status_code)
r = adm.put("settings/billing-policy", json={"billing_months": ["10", "09", "11", "06"], "month_due_at_enrollment": "09", "expected_version": bp.get("version")}, headers=k())
check("Mois enregistrés dans l'ordre de l'année scolaire", r.status_code == 200 and r.json().get("billing_months") == ["09", "10", "11", "06"], r.text[:120])
r2 = adm.put("settings/billing-policy", json={"billing_months": ["09"], "month_due_at_enrollment": None, "expected_version": None}, headers=k())
check("Modification concurrente des mois (version périmée) refusée", r2.status_code == 409, r2.status_code)

# ---------- copy to the next year ----------
y2 = ok(adm.post("settings/academic-years", json={"code": "2027-2028", "label": "2027-2028", "start_date": "2027-09-01", "end_date": "2028-06-30"}, headers=k()))
cp = adm.post(f"settings/academic-years/{y2['id']}/copy-configuration", json={"source_year_id": y["id"]}, headers=k())
copied = [t for t in adm.get("settings/tariffs", params={"year_id": y2["id"]}).json() if t["enabled"]]
statuses = {t["status"] for t in copied}
feb = [t for t in copied if t["effective_from"] == "2028-02-01"]
check("Copie vers l'année suivante : les montants actifs passent « en attente du barème officiel »", cp.status_code in (200, 201) and copied and statuses == {"PENDING_OFFICIAL"}, statuses)
check("Copie : dates d'effet décalées sur la nouvelle année (février 2027 → février 2028)", len(feb) == 1 and feb[0]["amount"] == "61000.00", [t["effective_from"] for t in copied][:8])
check("Copie : une règle de classe vise la classe de la nouvelle année", all(t["scope_ref"] != h1c["id"] for t in copied if t["scope_type"] == "CLASS"))

# ---------- isolation ----------
a_admin = user_client(state["A"], "ADMIN")
r = a_admin.get("settings/tariffs/resolve", params={"class_id": h1c["id"], "fee_type_id": fee["id"]})
check("Autre école : résolution sur une classe de l'école L1 refusée (404)", r.status_code == 404, r.status_code)
check("Autre école : aucune règle de l'école L1 listée", all(t["fee_type_id"] != fee["id"] for t in a_admin.get("settings/tariffs").json()))

# ---------- audit and closed year ----------
with owner.connect() as conn:
    upd = conn.execute(text("""SELECT count(*) FROM audit_events WHERE action='TARIFF_RULE_UPSERTED' AND school_id=:s AND old_json IS NOT NULL"""),
                       {"s": school["school_id"]}).scalar_one()
check("Audit : une mise à jour de règle garde l'ancienne valeur", upd >= 2, upd)
yy = next(x for x in adm.get("settings/academic-years").json() if x["id"] == y["id"])
ok(adm.post(f"settings/academic-years/{y['id']}/close", headers=k({"If-Match": str(yy["version"])})))
check("Année clôturée : plus aucune règle tarifaire modifiable", rule("SCHOOL", None, "99999").status_code in (409, 422))

passed = sum(r["pass"] for r in results)
out = Path(__file__).with_name("tariff-rules-live.json")
out.write_text(json.dumps(results, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} PASS -> {out.name}")
sys.exit(0 if passed == len(results) else 1)
