"""Local probe of the platform Schools module (lot 2026-10) against the running local API (recette data).

Real HTTP with real sign-in + TOTP (local recette fixtures). Prints PASS/FAIL lines; never prints a secret.
Covers: server-generated EduSync code + idempotent double submit, validation, instant search (accents, case,
spaces), status / configuration filters, keyset pagination (no duplicate, no gap), sorts, school sheet, edit with
optimistic concurrency, contextual statuses, administrator bootstrap (temporary password shown once, replay does not
return it), access reset (step-up), platform boundary (no local business role), CSV export, RBAC (restricted role,
direct API calls), audit trail. Usage: python tools/local/schools_module_probe.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src"))
from edusync.shared.infrastructure.mfa import current_step, totp_code  # noqa: E402

API = "http://127.0.0.1:58100/api/v1"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def call(method, path, token=None, body=None, headers=None, raw=False):
    h = {"Content-Type": "application/json", "Origin": "http://localhost:5180", **({"Authorization": f"Bearer {token}"} if token else {}), **(headers or {})}
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
            return r.status, (data if raw else json.loads(data or b"{}")), int((time.perf_counter() - t0) * 1000)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}"), int((time.perf_counter() - t0) * 1000)
        except Exception:
            return e.code, {}, 0


def wait_window():
    while time.time() % 30 > 25:
        time.sleep(0.5)


def login(email, password):
    code, step, _ = call("POST", "/auth/login", body={"email": email, "password": password, "scope": "PLATFORM"})
    secret = FX["MFA_TOTP"][email]["secret"]
    for _ in range(3):
        wait_window()
        code, sess, _ = call("POST", "/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": totp_code(secret, current_step())})
        if code == 200:
            return sess["access_token"], secret
        time.sleep(31)
    raise SystemExit(f"connexion impossible pour {email}")


def step_up(token, secret):
    time.sleep(31)
    wait_window()
    return call("POST", "/auth/platform/mfa/step-up", token, {"code": totp_code(secret, current_step())})[0] == 200


manager, msecret = login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"])
support, _ = login(FX["N1_TEAM"]["u2"]["email"], FX["N1_TEAM"]["u2"]["password"])
tag = uuid.uuid4().hex[:6].upper()

# ---------------------------------------------------------------- creation
key = str(uuid.uuid4())
body = {"name": f"Collège Sainte-Thérèse {tag}", "province": "kasai central", "city": "Kananga", "address": "Av. de la Paix 12, Q. Malandi",
        "contact_name": f"Mme Béatrice Ilunga {tag}", "contact_function": "Promotrice", "contact_phone": "081 234 5678", "contact_email": "promotrice@example.test"}
c1, s1, _ = call("POST", "/platform/schools", manager, body, {"Idempotency-Key": key})
c2, s2, _ = call("POST", "/platform/schools", manager, body, {"Idempotency-Key": key})
check(c1 == 201 and s1.get("code", "").startswith("EDS-") and len(s1["code"]) == 10, f"création : code généré par le serveur ({s1.get('code')})")
check(c2 in (200, 201) and s2.get("id") == s1.get("id"), "double validation (même clé) : une seule école")
check(s1.get("province") == "Kasaï-Central" and s1.get("contact_phone") == "+243812345678", "province normalisée sur le référentiel, téléphone en E.164")
c3, s3, _ = call("POST", "/platform/schools", manager, {**body, "name": body["name"] + " B"}, {"Idempotency-Key": str(uuid.uuid4())})
check(c3 == 201 and s3["code"] != s1["code"], f"code unique pour une seconde école ({s3.get('code')})")
for bad, label in ((dict(body, name=" "), "nom vide"), (dict(body, province="Katanga"), "province hors référentiel"),
                   (dict(body, province=""), "province vide"), (dict(body, contact_phone="12345"), "téléphone invalide"),
                   (dict(body, contact_email="pas-un-mail"), "e-mail invalide"), (dict(body, code="PIRATE"), "code imposé ignoré")):
    code, resp, _ = call("POST", "/platform/schools", manager, bad, {"Idempotency-Key": str(uuid.uuid4())})
    if label == "code imposé ignoré":
        check(code == 201 and resp.get("code", "").startswith("EDS-"), "un code fourni par le client est ignoré")
    else:
        check(code == 422, f"refus : {label} ({code})")
check(call("POST", "/platform/schools", support, body, {"Idempotency-Key": str(uuid.uuid4())})[0] == 403, "RBAC : rôle sans platform.schools.create → 403 (API directe)")

# ---------------------------------------------------------------- search / filters / pagination
code, r, ms = call("GET", f"/platform/schools-page?q={urllib.request.quote('sainte therese ' + tag.lower())}", manager)
check(code == 200 and r["total"] >= 2 and all(tag in i["name"] for i in r["items"]), f"recherche sans accents ni casse ({r.get('total')} résultats, {ms} ms)")
code, r, _ = call("GET", f"/platform/schools-page?q={urllib.request.quote('  ILUNGA ' + tag + '  ')}", manager)
check(code == 200 and r["total"] >= 2, "recherche sur le promoteur, espaces tolérés")
code, r, _ = call("GET", "/platform/schools-page?q=zzzzaucuneecole", manager)
check(code == 200 and r["total"] == 0 and r["items"] == [], "recherche sans résultat")
for st in ("ACTIVE", "SUSPENDED", "DISABLED"):
    code, r, _ = call("GET", f"/platform/schools-page?status={st}&limit=100", manager)
    check(code == 200 and all(i["status"] == st for i in r["items"]), f"filtre statut {st} ({r.get('total')})")
check(call("GET", "/platform/schools-page?status=EN_CONFIGURATION", manager)[0] == 422, "statut inventé refusé")
for cf in ("COMPLETE", "INCOMPLETE", "ADMIN_PENDING", "ADMIN_MISSING"):
    code, r, _ = call("GET", f"/platform/schools-page?config={cf}&limit=100", manager)
    check(code == 200 and all(i["config_state"] == cf for i in r["items"]), f"filtre configuration {cf} ({r.get('total')})")
for sort in ("name", "created", "status"):
    seen, cursor, pages, total, slow = [], None, 0, None, 0
    while True:
        code, r, ms = call("GET", f"/platform/schools-page?sort={sort}&limit=40" + (f"&cursor={cursor}" if cursor else ""), manager)
        if code != 200:
            break
        total = r["total"]; seen += [i["id"] for i in r["items"]]; pages += 1; slow = max(slow, ms)
        cursor = r["next_cursor"]
        if not cursor:
            break
    check(len(seen) == total and len(set(seen)) == total, f"pagination par curseur (tri {sort}) : {pages} pages, {total} écoles, ni doublon ni trou (max {slow} ms)")
check(call("GET", "/platform/schools-page?cursor=Zm9yZ2Vk", manager)[0] == 422, "curseur forgé refusé")
code, r, _ = call("GET", "/platform/dashboard", manager)
code2, r2, _ = call("GET", "/platform/schools-page?needs_admin=true&limit=1", manager)
na = next((w["count"] for w in r["watchlist"] if w["key"] == "schools_without_admin"), 0)
check(r2["total"] == na, f"cohérence tableau de bord : écoles actives sans administrateur {na} = {r2['total']}")

# ---------------------------------------------------------------- sheet / edit
sid = s1["id"]
code, d, ms = call("GET", f"/platform/schools/{sid}/detail", manager)
check(code == 200 and d["config_state"] == "ADMIN_MISSING" and d["school"]["contact_name"].startswith("Mme") and d["history"] is not None,
      f"fiche : contact séparé, configuration « administrateur à créer », historique ({ms} ms)")
code, u, _ = call("PATCH", f"/platform/schools/{sid}", manager, {**body, "province": "Kasaï-Central", "contact_function": "Promotrice et directrice", "version": d["school"]["version"]})
check(code == 200 and "contact_function" in u["changed"], "modification de l’identité (version optimiste)")
check(call("PATCH", f"/platform/schools/{sid}", manager, {**body, "version": d["school"]["version"]})[0] == 409, "modification concurrente refusée (409)")
check(call("PATCH", f"/platform/schools/{sid}", support, {**body, "version": u["version"]})[0] == 403, "RBAC : rôle sans platform.schools.update → 403")
code, ds, _ = call("GET", f"/platform/schools/{sid}/detail", support)
check(code == 200 and ds["history"] is None, "rôle sans audit : fiche sans historique de gouvernance")

# ---------------------------------------------------------------- administrator: bootstrap, replay, reset, boundary
check(step_up(manager, msecret), "code de confirmation (action sensible)")
akey = str(uuid.uuid4())
admin_body = {"full_name": f"Admin {tag}", "email": f"admin-{tag.lower()}@example.test", "delivery": "TEMPORARY"}
c1, a1, _ = call("POST", f"/platform/schools/{sid}/bootstrap-admin", manager, admin_body, {"Idempotency-Key": akey})
c2, a2, _ = call("POST", f"/platform/schools/{sid}/bootstrap-admin", manager, admin_body, {"Idempotency-Key": akey})
check(c1 == 201 and isinstance(a1.get("temporary_password"), str) and len(a1["temporary_password"]) == 14, "administrateur initial : mot de passe provisoire généré par le serveur, affiché une fois")
check(c2 in (200, 201) and a2.get("temporary_password") is None and a2.get("membership_id") == a1.get("membership_id"), "rejeu : même administrateur, mot de passe jamais renvoyé")
code, d, _ = call("GET", f"/platform/schools/{sid}/detail", manager)
check(d["config_state"] == "ADMIN_PENDING" and d["admins"][0]["state"] == "PENDING", "configuration « invitation en attente » tant que le mot de passe provisoire n’est pas remplacé")
code, rs, _ = call("POST", f"/platform/schools/{sid}/admins/{a1['membership_id']}/reset-access", manager, {"reason": "Téléphone perdu par l’administrateur", "delivery": "TEMPORARY"})
check(code == 200 and isinstance(rs.get("temporary_password"), str), "continuité : réinitialisation de l’accès administrateur (nouveau mot de passe provisoire, sessions fermées)")
check(call("POST", f"/platform/schools/{sid}/admins/{a1['membership_id']}/reset-access", support, {"reason": "essai interdit"})[0] == 403, "RBAC : réinitialisation refusée au rôle restreint")
check(call("POST", f"/platform/memberships/{a1['membership_id']}/roles", manager, {"role_code": "CAISSIER", "reason": "essai de rôle métier"})[0] == 403,
      "frontière : la plateforme ne peut pas attribuer un rôle métier local (caissier)")
check(call("POST", f"/platform/schools/{sid}/suspend", support, {"reason": "essai"}, {"Idempotency-Key": str(uuid.uuid4())})[0] == 403, "RBAC : suspension refusée au rôle restreint (API directe)")

# ---------------------------------------------------------------- export + audit
code, csv, _ = call("GET", f"/platform/schools/export.csv?q={tag}", manager, raw=True)
text_ = csv.decode("utf-8-sig") if code == 200 else ""
check(code == 200 and text_.count("\n") == 4 and "EDS-" in text_ and "Kasaï-Central" in text_, "export CSV de la liste filtrée (3 écoles + en-tête)")
code, au, _ = call("GET", f"/platform/audit?q={tag}&limit=50", manager)
actions = {i.get("action") for i in au.get("items", [])} if code == 200 else set()
code, au2, _ = call("GET", "/platform/audit?limit=50", manager)
actions |= {i.get("action") for i in au2.get("items", [])} if code == 200 else set()
check({"SCHOOL_CREATED", "PLATFORM_SCHOOL_UPDATED", "SCHOOL_ADMIN_BOOTSTRAPPED", "PLATFORM_SCHOOL_ADMIN_ACCESS_RESET", "PLATFORM_SCHOOLS_EXPORTED"} <= actions,
      "journal d’audit : création, modification, administrateur, réinitialisation, export")
print(f"\nRÉSULTAT : {'PASS' if FAILS == 0 else f'FAIL ({FAILS})'}")
sys.exit(1 if FAILS else 0)
