"""Live probe — prerequisites 1.1 to 1.4 of the N0/N1 certification (real API + PostgreSQL, isolated local instance).

1.1 persistent session (no periodic re-authentication), rotation, reuse detection, revocation, logout-all, CSRF origin
1.2 exact money JSON (Decimal, never float)
1.3 dedicated worker role (negative privileges)
1.4 platform account: own password, own devices, logout-all, audit
Also: sign-in without school code (scope AUTO) and post-authentication context choice.
"""
import json
import os
import secrets
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, call, ensure_user, login, must, owner, platform, save, state  # noqa: E402

COOKIE = "edusync_session"
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def raw_login(body, headers=None):
    return httpx.post(BASE + "/auth/login", json=body, headers=headers or {}, timeout=30)


def refresh_with(raw, headers=None):
    return httpx.post(BASE + "/auth/refresh", cookies={COOKIE: raw}, headers=headers or {}, timeout=30)


def sid_of(token):
    return jwt.decode(token, options={"verify_signature": False})["sid"]


def row(sid):
    with owner.connect() as c:
        return c.execute(text("SELECT revoked_at,revoked_reason,expires_at FROM user_device_sessions WHERE id=:id"), {"id": sid}).mappings().one()


A, B = state["A"], state["B"]

# ---------- AUTO sign-in (no school code) ----------
u1 = ensure_user(A, "N1_AUTO_ONE", ("CAISSIER",))
r = raw_login({"email": u1["email"], "password": u1["password"]})
check("AUTO : compte mono-école connecté sans code établissement", r.status_code == 200 and r.json().get("scope") == "SCHOOL" and r.json()["school"]["code"] == A["code"].upper(), r.status_code)
check("AUTO : cookie de session posé", bool(r.cookies.get(COOKIE)))

mgr_email, mgr_pass = os.environ["EDUSYNC_PLATFORM_ADMIN_EMAIL"], os.environ["EDUSYNC_PLATFORM_ADMIN_PASSWORD"]
r = raw_login({"email": mgr_email, "password": mgr_pass})
check("AUTO : Manager plateforme seul contexte -> Atelier Pro", r.status_code == 200 and r.json().get("scope") == "PLATFORM", r.status_code)

# Same account member of two schools -> explicit choice, and no session before the choice.
multi = state.setdefault("N1_MULTI", {})
if "email" not in multi:
    multi.update(email=f"n1-multi-{uuid4().hex[:8]}@example.test", password=secrets.token_urlsafe(24))
mgr = platform()
for school in (A, B):
    if school["code"] not in multi.setdefault("schools", []):
        rr = mgr.post(f"platform/schools/{school['school_id']}/bootstrap-admin", json={"email": multi["email"], "full_name": "Agent multi-écoles", "password": multi["password"]}, headers={"Idempotency-Key": str(uuid4())})
        if rr.status_code in (200, 201):
            multi["schools"].append(school["code"])
from common import save, settle_first_password  # noqa: E402
state["N1_MULTI"] = multi
save()
settle_first_password(multi)  # a fresh account created by the platform first chooses its own password
with owner.connect() as c:
    before = c.execute(text("SELECT count(*) FROM user_device_sessions s JOIN users u ON u.id=s.user_id WHERE u.email=:e"), {"e": multi["email"]}).scalar_one()
r = raw_login({"email": multi["email"], "password": multi["password"]})
body = r.json() if r.status_code == 200 else {}
check("AUTO : compte multi-écoles -> choix demandé", r.status_code == 200 and body.get("choice_required") is True and len(body.get("contexts", [])) >= 2, f"{r.status_code} {list(body)}")
check("AUTO : aucun jeton ni cookie avant le choix", "access_token" not in body and not r.cookies.get(COOKIE))
with owner.connect() as c:
    after = c.execute(text("SELECT count(*) FROM user_device_sessions s JOIN users u ON u.id=s.user_id WHERE u.email=:e"), {"e": multi["email"]}).scalar_one()
check("AUTO : aucune session créée avant le choix", after == before, f"{before}->{after}")
r = raw_login({"email": multi["email"], "password": multi["password"], "scope": "SCHOOL", "school_code": B["code"]})
check("AUTO : choix explicite d'une école -> session de cette école", r.status_code == 200 and r.json()["school"]["code"] == B["code"].upper(), r.status_code)
bad = raw_login({"email": multi["email"], "password": "mauvais-mot-de-passe"})
unknown = raw_login({"email": f"inconnu-{uuid4().hex[:6]}@example.test", "password": "x"})
check("AUTO : mauvais mot de passe et compte inconnu -> même réponse (pas d'énumération)", bad.status_code == unknown.status_code == 401 and bad.json() == unknown.json(), f"{bad.status_code}/{unknown.status_code}")
check("AUTO : mauvais mot de passe ne révèle pas les contextes", "contexts" not in bad.text)

# ---------- 1.1 persistent session ----------
c = login(u1["email"], u1["password"], "SCHOOL", A["code"])
raw = c.cookies.get(COOKIE)
sid = sid_of(c.headers["Authorization"].split()[1])
check("1.1 session sans expiration absolue imposée (expires_at NULL)", row(sid)["expires_at"] is None)
with owner.begin() as conn:
    conn.execute(text("UPDATE user_device_sessions SET created_at=now()-interval '400 days', last_seen_at=now()-interval '120 days' WHERE id=:id"), {"id": sid})
r1 = refresh_with(raw)
check("1.1 session de 400 jours inactive 120 jours : toujours renouvelée (pas de reconnexion périodique)", r1.status_code == 200, r1.status_code)
new = r1.cookies.get(COOKIE)
check("1.1 rotation du jeton à chaque renouvellement", bool(new) and new != raw)
sc = [h for h in r1.headers.get_list("set-cookie") if h.startswith(COOKIE)]
check("1.1 cookie HttpOnly, SameSite=Lax, chemin /api/v1/auth", bool(sc) and "HttpOnly" in sc[0] and "SameSite=lax" in sc[0] and "Path=/api/v1/auth" in sc[0], sc[0][-140:] if sc else "")
with owner.begin() as conn:
    conn.execute(text("UPDATE user_device_sessions SET previous_valid_until=now()-interval '1 second' WHERE id=:id"), {"id": sid})
check("1.1 jeton tourné rejoué hors grâce : refusé", refresh_with(raw).status_code == 401)
check("1.1 réutilisation : session entière révoquée", row(sid)["revoked_reason"] == "ROTATED_TOKEN_REUSED", row(sid)["revoked_reason"])
check("1.1 réutilisation : jeton d'accès coupé", httpx.get(BASE + "/auth/me", headers={"Authorization": c.headers["Authorization"]}).status_code == 401)

# CSRF origin on cookie endpoints.
c = login(u1["email"], u1["password"], "SCHOOL", A["code"])
raw = c.cookies.get(COOKIE)
check("1.1 CSRF : refresh depuis une origine étrangère refusé", refresh_with(raw, {"Origin": "https://evil.example"}).status_code == 403)
check("1.1 CSRF : refresh cross-site sans Origin refusé", refresh_with(raw, {"Sec-Fetch-Site": "cross-site"}).status_code == 403)
check("1.1 CSRF : login depuis une origine étrangère refusé", raw_login({"email": u1["email"], "password": u1["password"]}, {"Origin": "https://evil.example"}).status_code == 403)
lo = httpx.post(BASE + "/auth/logout", cookies={COOKIE: raw}, headers={"Origin": "https://evil.example"}, timeout=30)
check("1.1 CSRF : logout étranger refusé, session intacte", lo.status_code == 403 and refresh_with(raw).status_code == 200, lo.status_code)

# Multi-device + logout-all + deactivation.
d1 = login(u1["email"], u1["password"], "SCHOOL", A["code"])
d2 = login(u1["email"], u1["password"], "SCHOOL", A["code"])
la = httpx.post(BASE + "/auth/logout-all", cookies={COOKIE: d1.cookies.get(COOKIE)}, timeout=30)
check("1.1 déconnexion de tous les appareils (204)", la.status_code == 204, la.status_code)
check("1.1 logout-all : l'autre appareil est coupé", httpx.get(BASE + "/auth/me", headers={"Authorization": d2.headers["Authorization"]}).status_code == 401 and refresh_with(d2.cookies.get(COOKIE)).status_code == 401)
with owner.connect() as conn:
    audited = conn.execute(text("SELECT count(*) FROM audit_events WHERE action='SESSIONS_REVOKED_ALL' AND actor_user_id=(SELECT id FROM users WHERE email=:e)"), {"e": u1["email"]}).scalar_one()
check("1.1 logout-all audité", audited >= 1, audited)

# ---------- 1.4 platform account ----------
p = login(mgr_email, mgr_pass, "PLATFORM")
p2 = login(mgr_email, mgr_pass, "PLATFORM")
s = p.get("auth/platform/sessions")
items = s.json().get("items", []) if s.status_code == 200 else []
check("1.4 Manager : liste de ses appareils", s.status_code == 200 and len(items) >= 2, s.status_code)
check("1.4 Manager : appareil courant signalé", any(i.get("current") for i in items))
other = sid_of(p2.headers["Authorization"].split()[1])
rv = must(p, "POST", f"auth/platform/sessions/{other}/revoke", 204)
check("1.4 Manager : révocation d'un appareil -> coupé immédiatement", p2.get("platform/dashboard").status_code == 401)
check("1.4 Manager : révocation auditée", owner.connect().execute(text("SELECT count(*) FROM audit_events WHERE action='SESSION_REVOKED' AND new_json->>'session_id'=:s"), {"s": other}).scalar_one() == 1)
foreign = login(u1["email"], u1["password"], "SCHOOL", A["code"])
fsid = sid_of(foreign.headers["Authorization"].split()[1])
p.post(f"auth/platform/sessions/{fsid}/revoke", headers={"Idempotency-Key": str(uuid4())})
check("1.4 Manager : ne peut pas révoquer la session d'un autre compte (BOLA)", row(fsid)["revoked_at"] is None)
check("1.4 compte école : route mot de passe plateforme refusée", foreign.post("auth/platform/password", json={"current_password": "x", "new_password": "y" * 12}).status_code in (401, 403))
# Password change on a disposable platform collaborator is covered by n1 probes; here, wrong current password:
wr = p.post("auth/platform/password", json={"current_password": "pas-le-bon", "new_password": secrets.token_urlsafe(16)}, headers={"Idempotency-Key": str(uuid4())})
check("1.4 Manager : mauvais mot de passe actuel refusé sans révoquer", wr.status_code == 400 and p.get("platform/dashboard").status_code == 200, wr.status_code)

# ---------- 1.2 exact money JSON ----------
admin = ensure_user(A, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
ac = login(admin["email"], admin["password"], "SCHOOL", A["code"])
fee = state.setdefault("N1_DECIMAL_FEE", {})
if "id" not in fee:
    code = "DEC" + uuid4().hex[:5].upper()
    fr = must(ac, "POST", "settings/fee-types", (200, 201), json={"code": code, "label": "Frais décimal recette", "periodicity": "OPTIONAL", "default_currency": "USD"})
    fee["id"] = fr.json()["id"]
    save()
# One tariff rule per target and date (Desktop parity, lot L1): the USD amount targets the class, the CDF one the section.
for currency, amount, target in (("USD", "12345.67", {"class_id": A["class_id"]}), ("CDF", "1500000.05", {"section_id": A["section_id"]})):
    tr = call(ac, "POST", "settings/tariffs", json={"academic_year_id": A["year_id"], "fee_type_id": fee["id"], **target, "currency": currency, "amount": amount})
    got = tr.json().get("amount") if tr.status_code in (200, 201) else None
    if tr.status_code == 409:
        got = next((t["amount"] for t in ac.get("settings/tariffs").json() if t["fee_type_id"] == fee["id"] and t["currency"] == currency), None)
    check(f"1.2 montant {currency} {amount} : aller-retour exact en chaîne (pas de float)", isinstance(got, str) and got == amount, f"{tr.status_code} {got!r}")
raw_json = ac.get("settings/tariffs").text
check("1.2 aucune représentation flottante binaire dans la réponse JSON", '"amount":12345.67' not in raw_json and "e+" not in raw_json)

# ---------- 1.3 worker role ----------
wurl = os.environ["EDUSYNC_WORKER_DATABASE_URL"]
weng = create_engine(wurl, pool_size=1)
with weng.connect() as wc:
    attrs = wc.execute(text("SELECT rolsuper,rolbypassrls,rolcreaterole,rolcreatedb FROM pg_roles WHERE rolname=current_user")).one()
    check("1.3 rôle worker : NOSUPERUSER NOBYPASSRLS NOCREATEROLE NOCREATEDB", not any(attrs), str(attrs))
    owns = wc.execute(text("SELECT count(*) FROM pg_tables WHERE tableowner=current_user")).scalar_one()
    check("1.3 rôle worker : propriétaire d'aucune table", owns == 0, owns)
for label, stmt in (("lecture users", "SELECT count(*) FROM users"), ("lecture élèves", "SELECT count(*) FROM students"),
                    ("lecture paiements", "SELECT count(*) FROM finance_payments"), ("insertion outbox", "INSERT INTO outbox_events(id) VALUES (gen_random_uuid())"),
                    ("suppression livraisons", "DELETE FROM communication_deliveries"), ("DDL", "CREATE TABLE worker_probe(x int)")):
    try:
        with weng.begin() as wc:
            wc.execute(text(stmt))
        check(f"1.3 rôle worker : {label} refusé", False, "autorisé")
    except Exception as e:  # noqa: BLE001
        check(f"1.3 rôle worker : {label} refusé", "permission" in str(e).lower() or "droit" in str(e).lower() or "refus" in str(e).lower(), type(e).__name__)
with weng.connect() as wc:
    n = wc.execute(text("SELECT count(*) FROM outbox_events")).scalar_one()
check("1.3 rôle worker : lecture de sa file autorisée", n >= 0)

out = Path(__file__).with_name("prereq-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
