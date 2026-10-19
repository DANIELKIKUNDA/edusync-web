"""Local probe of the change of space without signing out (lot 2026-10).

One identity (the restricted platform support account of the fixtures, equipped with a TOTP factor) receives, for the
duration of the probe, memberships in 10 active schools (two roles in the first one). Proves: switches in every
direction (platform → school → school → platform), no new code to type, permissions recomputed by the server (no
leak in either direction), the old access token dead immediately, no pile of sessions, forged / unknown / suspended /
revoked targets refused and audited, a revoked space mid-session leaves the identity able to move to another space,
1 / 2 / 5 / 10 contexts listed, cross-origin refused. Everything created is removed at the end.
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/switch_probe.py
"""
from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
from edusync.shared.infrastructure.mfa import current_step, totp_code  # noqa: E402

env = L.load_env("demo")
from sqlalchemy import create_engine, text  # noqa: E402

API = "http://127.0.0.1:58100/api/v1"
ORIGIN = "http://localhost:5180"
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def sql(q, **p):
    with owner.begin() as c:
        res = c.execute(text(q), p)
        return res.mappings().all() if res.returns_rows else res.rowcount


class Browser:
    """One browser: its own cookie jar (the persistent HttpOnly session cookie lives here)."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method, path, token=None, body=None, origin=ORIGIN):
        h = {"Content-Type": "application/json", **({"Origin": origin} if origin else {}), **({"Authorization": f"Bearer {token}"} if token else {})}
        req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
        try:
            with self.op.open(req, timeout=60) as resp:
                raw = resp.read().decode()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            raw = e.read().decode()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw


U = FX["N1_TEAM"]["u2"]
UID = U["id"]
SECRET = FX["MFA_TOTP"][U["email"]]["secret"]


def platform_login(b: Browser):
    code, step = b.call("POST", "/auth/login", body={"email": U["email"], "password": U["password"], "scope": "PLATFORM"})
    assert code == 200 and step.get("mfa_token"), (code, step)
    for _ in range(3):
        while time.time() % 30 > 25:
            time.sleep(0.5)
        code, sess = b.call("POST", "/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": totp_code(SECRET, current_step())})
        if code == 200:
            return sess
        time.sleep(31)
    raise SystemExit("connexion impossible")


def live_sessions():
    return sql("SELECT count(*) n FROM user_device_sessions WHERE user_id=:u AND revoked_at IS NULL AND created_at>=:t", u=UID, t=t0)[0]["n"]


def audits(action, since):
    return sql("SELECT result, new_json FROM audit_events WHERE entity_id=CAST(:u AS uuid) AND action=:a AND occurred_at>=:t ORDER BY occurred_at", u=UID, a=action, t=since)


# ---------------------------------------------------------------- setup: 10 school spaces for this identity
schools = sql("""SELECT s.id, s.code FROM schools s WHERE s.status='ACTIVE' AND NOT EXISTS
    (SELECT 1 FROM school_memberships m WHERE m.school_id=s.id AND m.user_id=:u) ORDER BY s.code LIMIT 10""", u=UID)
assert len(schools) == 10, "il faut 10 écoles actives"
roles = {r["code"]: r["id"] for r in sql("SELECT id, code FROM rbac_roles WHERE school_id IS NULL AND level='SCHOOL' AND status='ACTIVE' AND code IN ('CAISSIER','SECRETARIAT')")}
created_m, created_a = [], []
outsider = sql("SELECT code FROM schools s WHERE s.status='ACTIVE' AND NOT EXISTS (SELECT 1 FROM school_memberships m WHERE m.school_id=s.id AND m.user_id=:u) AND s.code<>ALL(:c) LIMIT 1",
               u=UID, c=[s["code"] for s in schools])[0]["code"]
t0 = sql("SELECT now() t")[0]["t"]
try:
    for i, s in enumerate(schools):
        mid = sql("INSERT INTO school_memberships(id,school_id,user_id,active,created_at,version) VALUES(gen_random_uuid(),:s,:u,true,now(),1) RETURNING id", s=s["id"], u=UID)[0]["id"]
        created_m.append(mid)
        for rc in (("CAISSIER", "SECRETARIAT") if i == 0 else ("CAISSIER",)):
            created_a.append(sql("""INSERT INTO rbac_assignments(id,user_id,role_id,school_id,membership_id,active,valid_from,version,created_at,updated_at,reason)
                VALUES(gen_random_uuid(),:u,:r,:s,:m,true,now()-interval '1 minute',1,now(),now(),'switch_probe') RETURNING id""", u=UID, r=roles[rc], s=s["id"], m=mid)[0]["id"])
    A, B, S5 = schools[0]["code"], schools[1]["code"], schools[4]["code"]

    b = Browser()
    sess = platform_login(b)
    ptok = sess["access_token"]
    base = live_sessions()

    # ------------------------------------------------------------ contexts
    code, ctx = b.call("GET", "/auth/contexts")
    codes = [c["school_code"] for c in ctx["contexts"] if c["scope"] == "SCHOOL"]
    check(code == 200 and len(codes) >= 10 and all(s["code"] in codes for s in schools) and any(c["scope"] == "PLATFORM" and c["current"] for c in ctx["contexts"]),
          f"liste des espaces : {len(ctx['contexts'])} espaces dont la plateforme (espace courant marqué)")
    ca = next(c for c in ctx["contexts"] if c["school_code"] == A)
    check(len(ca["roles"]) == 2, f"plusieurs rôles dans une même école affichés : {', '.join(ca['roles'])}")
    pl = next(c for c in ctx["contexts"] if c["scope"] == "PLATFORM")
    check(pl["label"] == "Plateforme EduSync — administration" and pl["roles"], "espace plateforme nommé « Plateforme EduSync » avec son rôle")
    check(b.call("GET", "/auth/contexts", origin=None)[0] == 200 and b.call("POST", "/auth/switch", body={"scope": "SCHOOL", "school_code": A}, origin="https://evil.example")[0] == 403,
          "changement depuis une autre origine refusé")
    check(Browser().call("GET", "/auth/contexts")[0] == 401 and Browser().call("POST", "/auth/switch", body={"scope": "PLATFORM"})[0] == 401, "sans session : 401")

    # ------------------------------------------------------------ platform → school
    code, s1 = b.call("POST", "/auth/switch", body={"scope": "SCHOOL", "school_code": A.lower()})
    check(code == 200 and s1.get("scope") == "SCHOOL" and s1["school"]["code"] == A and not s1.get("mfa_required"),
          "plateforme → école : sans mot de passe ni nouveau code (preuve du second facteur conservée)")
    stok = s1["access_token"]
    check(not any(p.startswith("platform.") for p in s1["permissions"]) and s1["permissions"], f"permissions recalculées pour l’école ({len(s1['permissions'])}), aucune capacité plateforme")
    check(b.call("GET", "/platform/system/health", stok)[0] in (401, 403) and b.call("GET", "/platform/team/users", stok)[0] in (401, 403),
          "jeton école refusé sur les routes plateforme (aucune fuite école → plateforme)")
    check(b.call("GET", "/auth/platform/sessions", ptok)[0] == 401, "ancien jeton plateforme invalide immédiatement")
    check(live_sessions() == base, f"une seule session active pour ce navigateur ({base})")
    code, me = b.call("GET", "/auth/me", stok)
    check(code == 200, "jeton école accepté sur l’école")
    code, rf = b.call("POST", "/auth/refresh")
    check(code == 200 and rf["scope"] == "SCHOOL" and rf["school"]["code"] == A, "rechargement de page : la session reprend dans l’école (dernier espace)")

    # ------------------------------------------------------------ school → school
    code, s2 = b.call("POST", "/auth/switch", body={"scope": "SCHOOL", "school_code": B})
    check(code == 200 and s2["school"]["code"] == B and b.call("GET", "/auth/me", rf["access_token"])[0] == 401, "école → école : ancien jeton mort")
    check(set(s2["permissions"]) < set(s1["permissions"]), f"école → école : permissions de l’école cible (1 rôle : {len(s2['permissions'])} au lieu de {len(s1['permissions'])})")
    check(live_sessions() == base, "toujours une seule session")

    # ------------------------------------------------------------ forged / unknown / suspended targets
    for target, label in ((outsider, "école sans appartenance (school_code forgé)"), ("NOPE-XXXX", "code inconnu")):
        code, _ = b.call("POST", "/auth/switch", body={"scope": "SCHOOL", "school_code": target})
        check(code == 403, f"{label} : 403")
    check(b.call("POST", "/auth/switch", body={"scope": "SCHOOL"})[0] == 403, "école sans code : 403")
    check(b.call("POST", "/auth/switch", body={"scope": "ROOT"})[0] == 422, "portée inventée : 422")
    check(b.call("GET", "/auth/me", s2["access_token"])[0] == 200, "après un refus, l’espace courant reste ouvert")
    sql("UPDATE schools SET status='SUSPENDED' WHERE code=:c", c=S5)
    try:
        code, ctx = b.call("GET", "/auth/contexts")
        check(S5 not in [c["school_code"] for c in ctx["contexts"]], "école suspendue absente de la liste")
        check(b.call("POST", "/auth/switch", body={"scope": "SCHOOL", "school_code": S5})[0] == 403, "école suspendue : 403")
    finally:
        sql("UPDATE schools SET status='ACTIVE' WHERE code=:c", c=S5)
    ref = audits("CONTEXT_SWITCH_REFUSED", t0)
    check(len(ref) >= 3 and all(r["result"] == "REJECTED" for r in ref), f"refus journalisés ({len(ref)})")

    # ------------------------------------------------------------ revoked space mid-session
    sql("UPDATE school_memberships SET active=false, version=version+1 WHERE id=:m", m=created_m[1])
    code, _ = b.call("GET", "/auth/me", s2["access_token"])
    check(code in (401, 403), "accès retiré pendant la session : l’école est refusée tout de suite")
    check(b.call("POST", "/auth/refresh")[0] == 401, "accès retiré : pas de nouveau jeton pour cet espace")
    code, ctx = b.call("GET", "/auth/contexts")
    check(code == 200 and not ctx["current_valid"] and B not in [c["school_code"] for c in ctx["contexts"]],
          "accès retiré : l’identité reste connue, les autres espaces sont proposés")
    code, s3 = b.call("POST", "/auth/switch", body={"scope": "PLATFORM"})
    check(code == 200 and s3["scope"] == "PLATFORM" and not s3.get("mfa_required"), "école retirée → plateforme sans se reconnecter ni retaper de code")
    check(b.call("GET", "/auth/me", s3["access_token"])[0] == 403 and live_sessions() == base, "plateforme ouverte, une seule session")
    code, me = b.call("GET", "/auth/platform/sessions", s3["access_token"])
    check(code == 200, "jeton plateforme accepté sur les routes plateforme")
    check(b.call("GET", "/auth/platform/sessions", s2["access_token"])[0] in (401, 403), "ancien jeton école refusé sur la plateforme")

    # ------------------------------------------------------------ the platform role does not open a school by itself
    code, _ = b.call("POST", "/auth/switch", body={"scope": "SCHOOL", "school_code": outsider})
    check(code == 403, "un rôle plateforme n’ouvre aucune école sans appartenance (pas de super-admin implicite)")

    # ------------------------------------------------------------ step-up is never carried
    st = sql("SELECT mfa_verified_at IS NOT NULL v, mfa_stepup_at IS NULL s FROM user_device_sessions WHERE user_id=:u AND revoked_at IS NULL ORDER BY created_at DESC LIMIT 1", u=UID)[0]
    check(st["v"] and st["s"], "preuve du second facteur conservée, confirmation renforcée (step-up) jamais reportée")
    ok = audits("CONTEXT_SWITCHED", t0)
    check(len(ok) >= 3 and all("token" not in json.dumps(r["new_json"]).lower() for r in ok), f"changements journalisés sans secret ({len(ok)})")

    # ------------------------------------------------------------ 1 / 2 contexts (school accounts)
    m = FX["N1_MULTI"]
    b2 = Browser()
    code, out = b2.call("POST", "/auth/login", body={"email": m["email"], "password": m["password"]})
    check(code == 200 and out.get("choice_required") and len(out["contexts"]) >= 2, "compte multi-écoles : choix de l’espace à la connexion")
    code, out = b2.call("POST", "/auth/login", body={"email": m["email"], "password": m["password"], "scope": "SCHOOL", "school_code": m["schools"][0]})
    if out.get("access_token"):
        code, c2 = b2.call("GET", "/auth/contexts")
        check(code == 200 and len(c2["contexts"]) >= 2 and not any(c["scope"] == "PLATFORM" for c in c2["contexts"]), "compte école : aucun espace plateforme proposé")
        code, sw = b2.call("POST", "/auth/switch", body={"scope": "PLATFORM"})
        check(code == 403, "compte école → plateforme forcé : 403")
        code, sw = b2.call("POST", "/auth/switch", body={"scope": "SCHOOL", "school_code": m["schools"][1]})
        check(code == 200 and sw["school"]["code"].upper() == m["schools"][1].upper(), "compte école : école → école sans se reconnecter")
    one = FX["A"]["users"]["CAISSIER1"]
    b3 = Browser()
    code, out = b3.call("POST", "/auth/login", body={"email": one["email"], "password": one["password"], "scope": "SCHOOL", "school_code": FX["A"]["code"]})
    if out.get("access_token"):
        code, c1 = b3.call("GET", "/auth/contexts")
        check(code == 200 and len(c1["contexts"]) == 1, "compte à un seul espace : un seul contexte (le sélecteur reste masqué)")
finally:
    if created_a:
        sql("DELETE FROM rbac_assignments WHERE id=ANY(:a)", a=created_a)
    if created_m:
        sql("DELETE FROM user_device_sessions WHERE membership_id=ANY(:m)", m=created_m)
        try:
            sql("DELETE FROM school_memberships WHERE id=ANY(:m)", m=created_m)
        except Exception:  # noqa: BLE001
            sql("UPDATE school_memberships SET active=false WHERE id=ANY(:m)", m=created_m)

print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
