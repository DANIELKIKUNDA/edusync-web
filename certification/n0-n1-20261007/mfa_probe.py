"""Live probe — second factor of platform accounts (MFA_PROPOSAL.md, option B; mandate of 2026-10-13).

Runs against the isolated local instance (real API + PostgreSQL + Redis). Disposable platform accounts are created
through the public team API; their passwords and TOTP secrets stay in the private fixtures file under .local/ and
are never printed. Codes are computed by an RFC 6238 implementation independent of the application (common.totp).
"""
import json
import os
import secrets
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import jwt
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, MFA_STATE, ensure_school, ensure_user, fresh_code, login, owner, platform, save, state, totp  # noqa: E402

results = []
COOKIE = "edusync_session"


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def post(client, path, body):
    return client.post(path, json=body, headers={"Idempotency-Key": str(uuid4())})


def raw_login(email, password, **extra):
    return httpx.post(BASE + "/auth/login", json={"email": email, "password": password, **extra}, timeout=30)


def mfa(path, body, cookies=None):
    return httpx.post(BASE + "/auth/mfa/" + path, json=body, cookies=cookies, timeout=30)


def bearer(token):
    return httpx.Client(base_url=BASE + "/", headers={"Authorization": "Bearer " + token}, timeout=30)


run = uuid4().hex[:6]
mgr = platform()
mgr_email = os.environ["EDUSYNC_PLATFORM_ADMIN_EMAIL"]
fx = state.setdefault("MFA_PROBE", {})

# A disposable platform role to give: an ACTIVE non-Manager role the Manager fully holds, else a fresh custom one.
roles = mgr.get("platform/team/roles").json()["items"]
me_caps = set(mgr.get("platform/team/me").json()["permissions"])
role = next((r for r in roles if r["status"] == "ACTIVE" and r["code"] != "MANAGER_SYSTEME" and r["capabilities"] and set(r["capabilities"]) <= me_caps), None)
if role is None:
    code = f"MFAPROBE_{run.upper()}"
    rid = post(mgr, "platform/team/roles", {"code": code, "label": "Recette MFA", "capabilities": ["platform.schools.read"]}).json()["id"]
    post(mgr, f"platform/team/roles/{rid}/activate", {"reason": "Recette MFA : rôle jetable"})
    role = {"code": code}


def new_account(tag):
    email, password = f"mfa-{tag}-{run}@example.test", secrets.token_urlsafe(18)
    r = post(mgr, "platform/team/users", {"email": email, "full_name": f"Recette MFA {tag}", "password": password,
                                          "role_codes": [role["code"]], "reason": "Recette MFA : compte jetable"})
    assert r.status_code == 201, r.text[:200]
    return {"email": email, "password": password, "id": r.json()["id"]}


acc = new_account("a")
fx["acc"] = acc
save()

# ---------- 1. password step: no session before the second factor ----------
r = raw_login(acc["email"], acc["password"])
d = r.json()
check("Mot de passe seul : aucune session (ni jeton d'accès, ni cookie)", r.status_code == 200 and "access_token" not in d and not r.cookies.get(COOKIE), list(d))
check("Compte plateforme sans facteur : enrôlement obligatoire demandé", d.get("mfa_enrollment_required") is True and d.get("mfa_required") is False and d.get("scope") == "PLATFORM")
step_token = d["mfa_token"]
check("Jeton d'étape refusé comme jeton d'API (pas un jeton d'accès)", bearer(step_token).get("platform/team/me").status_code == 401)
check("Jeton d'étape d'enrôlement refusé par la vérification de connexion", mfa("verify", {"mfa_token": step_token, "code": "123456"}).status_code == 401)

# ---------- 2. enrolment ----------
st = mfa("enroll/start", {"mfa_token": step_token})
sd = st.json()
secret = sd.get("secret", "")
check("Enrôlement : QR code SVG local, clé manuelle, URI otpauth avec émetteur", st.status_code == 200 and sd["qr_svg"].lstrip().startswith("<svg")
      and sd["otpauth_uri"].startswith("otpauth://totp/") and "issuer=EduSync" in sd["otpauth_uri"] and len(secret) >= 32)
check("Enrôlement : réponse non mise en cache", "no-store" in st.headers.get("cache-control", ""))
check("Enrôlement : première saisie fausse refusée (400), facteur non activé", mfa("enroll/confirm", {"mfa_token": step_token, "code": "000000"}).status_code == 400)
with owner.connect() as c:
    pending = c.execute(text("SELECT status, secret_ciphertext FROM user_mfa_factors WHERE user_id=:u AND status<>'REVOKED'"), {"u": acc["id"]}).mappings().all()
check("Avant confirmation : facteur seulement en attente", [p["status"] for p in pending] == ["PENDING"], [p["status"] for p in pending])
check("Secret chiffré au repos (jamais en clair en base)", pending and secret not in pending[0]["secret_ciphertext"] and pending[0]["secret_ciphertext"].startswith("v1:"))
code0, step0 = fresh_code(secret, 0)
cf = mfa("enroll/confirm", {"mfa_token": step_token, "code": code0})
cd = cf.json()
codes = cd.get("recovery_codes", [])
check("Confirmation : session ouverte + 10 codes de secours affichés une fois", cf.status_code == 200 and cd.get("access_token") and len(codes) == 10 and cf.cookies.get(COOKIE), cf.status_code)
acc_token, acc_cookie = cd["access_token"], cf.cookies.get(COOKIE)
state.setdefault(MFA_STATE, {})[acc["email"]] = {"secret": secret, "last_step": step0, "recovery_codes": codes}
save()
check("Jeton d'étape consommé : réutilisation refusée", mfa("enroll/confirm", {"mfa_token": step_token, "code": code0}).status_code == 401)
check("Session obtenue utilisable sur l'Atelier Pro", bearer(acc_token).get("platform/team/me").status_code == 200)
with owner.connect() as c:
    sess = c.execute(text("SELECT mfa_method, mfa_verified_at FROM user_device_sessions WHERE user_id=:u AND revoked_at IS NULL"), {"u": acc["id"]}).mappings().all()
    stored = c.execute(text("SELECT code_hash FROM user_mfa_recovery_codes WHERE user_id=:u AND revoked_at IS NULL"), {"u": acc["id"]}).scalars().all()
check("Session marquée « second facteur validé » (TOTP)", len(sess) == 1 and sess[0]["mfa_method"] == "TOTP" and sess[0]["mfa_verified_at"] is not None)
check("Codes de secours stockés hachés (Argon2), jamais en clair", len(stored) == 10 and all(h.startswith("$argon2") for h in stored) and not any(c in "".join(stored) for c in codes))

# ---------- 3. sign-in with the factor ----------
r = raw_login(acc["email"], acc["password"])
d = r.json()
check("Compte enrôlé : code demandé (TOTP ou code de secours)", d.get("mfa_required") is True and set(d.get("methods", [])) == {"TOTP", "RECOVERY_CODE"})
check("Rejeu du code de l'enrôlement (même pas de 30 s) refusé", mfa("verify", {"mfa_token": d["mfa_token"], "code": code0}).status_code == 400)
# Sent well inside a 30 s step: computed at the very end of a step, "+2" would be only "+1" when the server reads it.
while not 3 <= time.time() % 30 <= 24:
    time.sleep(0.5)
far = mfa("verify", {"mfa_token": d["mfa_token"], "code": totp(secret, int(time.time() // 30) + 2)})
check("Code hors fenêtre (+2 pas = +60 s) refusé", far.status_code == 400, far.status_code)
check("Code et code de secours ensemble refusés (422)", mfa("verify", {"mfa_token": d["mfa_token"], "code": "123456", "recovery_code": codes[0]}).status_code == 422)
code1, step1 = fresh_code(secret, step0)
ok = mfa("verify", {"mfa_token": d["mfa_token"], "code": code1})
check("Bon code (pas suivant) : session ouverte", ok.status_code == 200 and ok.json().get("access_token"), ok.status_code)
state[MFA_STATE][acc["email"]]["last_step"] = step1
save()
check("Même code rejoué immédiatement sur une nouvelle étape : refusé", mfa("verify", {"mfa_token": raw_login(acc["email"], acc["password"]).json()["mfa_token"], "code": code1}).status_code == 400)

# ---------- 4. recovery codes ----------
d = raw_login(acc["email"], acc["password"]).json()
rc = mfa("verify", {"mfa_token": d["mfa_token"], "recovery_code": codes[0].lower().replace("-", " ")})
check("Code de secours accepté (casse et séparateurs tolérés), 9 restants", rc.status_code == 200 and rc.json().get("recovery_codes_remaining") == 9, rc.status_code)
d = raw_login(acc["email"], acc["password"]).json()
check("Code de secours déjà utilisé : refusé", mfa("verify", {"mfa_token": d["mfa_token"], "recovery_code": codes[0]}).status_code == 400)
c_acc = bearer(acc_token)
st_ = c_acc.get("auth/platform/mfa").json()
check("État MFA du compte : enrôlé, 9 codes restants, désactivation par soi-même impossible", st_["enrolled"] and st_["recovery_codes_remaining"] == 9 and st_["self_disable_allowed"] is False, st_)
check("Régénération sans code TOTP valide : refusée", c_acc.post("auth/platform/mfa/recovery-codes", json={"code": "000000"}).status_code == 400)
code2, step2 = fresh_code(secret, step1)
rg = c_acc.post("auth/platform/mfa/recovery-codes", json={"code": code2})
new_codes = rg.json().get("recovery_codes", [])
state[MFA_STATE][acc["email"]].update(last_step=step2, recovery_codes=new_codes)
save()
check("Régénération après code TOTP : 10 nouveaux codes", rg.status_code == 200 and len(new_codes) == 10 and not set(new_codes) & set(codes))
d = raw_login(acc["email"], acc["password"]).json()
check("Ancien code de secours non utilisé : invalidé par la régénération", mfa("verify", {"mfa_token": d["mfa_token"], "recovery_code": codes[1]}).status_code == 400)

# ---------- 5. no self-disable, no bypass by direct API call ----------
for verb in ("DELETE", "POST", "PUT"):
    rr = c_acc.request(verb, "auth/platform/mfa", json={"code": "123456"})
    check(f"Aucune route de désactivation par soi-même ({verb} /auth/platform/mfa)", rr.status_code in (404, 405), rr.status_code)
check("Réinitialisation de son propre facteur via l'équipe : refusée", post(c_acc, f"platform/team/users/{acc['id']}/mfa-reset", {"reason": "Je me retire mon MFA"}).status_code == 403)
mgr_id = mgr.get("platform/team/me").json()["user"]["id"]
check("Compte sans gouvernance d'équipe : réinitialiser le MFA d'un Manager refusé", post(c_acc, f"platform/team/users/{mgr_id}/mfa-reset", {"reason": "Escalade tentée"}).status_code == 403)

# A platform session that never passed the second factor (legacy row or any bypass) must reach nothing.
raw_cookie = secrets.token_urlsafe(48)
import hashlib  # noqa: E402
with owner.begin() as c:
    uv = c.execute(text("SELECT version FROM users WHERE id=:u"), {"u": acc["id"]}).scalar_one()
    sid = c.execute(text("""INSERT INTO user_device_sessions(user_id,token_hash,label,user_agent_hash,user_version)
        VALUES(:u,:h,'Session sans MFA (recette)',:h,:v) RETURNING id"""), {"u": acc["id"], "h": hashlib.sha256(raw_cookie.encode()).hexdigest(), "v": uv}).scalar_one()
forged = jwt.encode({"sub": acc["id"], "iss": os.environ.get("EDUSYNC_JWT_ISSUER", "edusync"), "aud": os.environ.get("EDUSYNC_JWT_AUDIENCE", "edusync-web"),
                     "iat": int(time.time()), "nbf": int(time.time()), "exp": int(time.time()) + 600, "jti": str(uuid4()), "typ": "access",
                     "scope": "platform", "user_version": uv, "sid": str(sid)}, os.environ["EDUSYNC_JWT_SECRET"], algorithm="HS256")
nb = bearer(forged).get("platform/team/me")
check("Jeton plateforme valide mais session sans second facteur : refusé (401)", nb.status_code == 401, nb.status_code)
check("Renouvellement d'une session sans second facteur : refusé", httpx.post(BASE + "/auth/refresh", cookies={COOKIE: raw_cookie}, timeout=30).status_code == 401)
check("Session persistante validée : renouvelée sans nouveau code (appareil approuvé)", httpx.post(BASE + "/auth/refresh", cookies={COOKIE: acc_cookie}, timeout=30).status_code == 200)

# ---------- 6. tenant isolation of the MFA tables ----------
tenant = create_engine(os.environ["EDUSYNC_TENANT_DATABASE_URL"])
try:
    with tenant.connect() as c:
        c.execute(text("SELECT count(*) FROM user_mfa_factors")).scalar_one()
    check("Rôle école (tenant) : lecture des secrets MFA impossible", False, "lecture permise")
except DBAPIError as e:
    check("Rôle école (tenant) : lecture des secrets MFA impossible", "permission" in str(e.orig).lower() or "droit" in str(e.orig).lower(), type(e.orig).__name__)

# ---------- 7. rate limiting and attempts ----------
lock = new_account("b")
r = raw_login(lock["email"], lock["password"])
tok = r.json()["mfa_token"]
s2 = mfa("enroll/start", {"mfa_token": tok}).json()["secret"]
c0, k0 = fresh_code(s2, 0)
done = mfa("enroll/confirm", {"mfa_token": tok, "code": c0})
state[MFA_STATE][lock["email"]] = {"secret": s2, "last_step": k0, "recovery_codes": done.json()["recovery_codes"]}
save()
tok = raw_login(lock["email"], lock["password"]).json()["mfa_token"]
seq = [mfa("verify", {"mfa_token": tok, "code": f"{i:06d}"}).status_code for i in range(1, 6)]
check("5 codes faux sur une étape : 4 refus puis étape annulée (reconnexion exigée)", seq == [400, 400, 400, 400, 401], seq)
tok = raw_login(lock["email"], lock["password"]).json()["mfa_token"]
good, _ = fresh_code(s2, k0)
locked = mfa("verify", {"mfa_token": tok, "code": good})
check("Compteur par compte (Redis) : même un bon code est refusé pendant le verrou (429 + Retry-After)", locked.status_code == 429 and int(locked.headers.get("retry-after", "0")) > 0, locked.status_code)
d_other = raw_login(acc["email"], acc["password"]).json()
code_o, step_o = fresh_code(secret, int(state[MFA_STATE][acc["email"]]["last_step"]))
other = mfa("verify", {"mfa_token": d_other["mfa_token"], "code": code_o})
state[MFA_STATE][acc["email"]]["last_step"] = step_o
save()
check("Verrou par compte seulement : un autre compte à la même adresse n'est pas bloqué", other.status_code == 200, other.status_code)
with owner.connect() as c:
    failed = c.execute(text("SELECT count(*) FROM audit_events WHERE action='MFA_FAILED' AND entity_id=:u AND result='REJECTED'"), {"u": lock["id"]}).scalar_one()
check("Chaque échec MFA audité (résultat REJECTED)", failed >= 5, failed)

# ---------- 8. reset by another Manager (lost phone) ----------
check("Réinitialisation sans motif : refusée (422)", post(mgr, f"platform/team/users/{acc['id']}/mfa-reset", {"reason": ""}).status_code == 422)
reason = f"Téléphone perdu — identité vérifiée par appel ({run})"
rs = post(mgr, f"platform/team/users/{acc['id']}/mfa-reset", {"reason": reason})
check("Manager : réinitialisation du facteur d'un autre compte, sessions plateforme coupées", rs.status_code == 200 and rs.json()["factors_revoked"] == 1 and rs.json()["sessions_revoked"] >= 1, rs.json())
check("Après réinitialisation : ancien jeton coupé immédiatement", bearer(acc_token).get("platform/team/me").status_code == 401)
d = raw_login(acc["email"], acc["password"]).json()
check("Après réinitialisation : nouvel enrôlement obligatoire à la connexion", d.get("mfa_enrollment_required") is True)
old = mfa("verify", {"mfa_token": d["mfa_token"], "code": totp(secret, int(time.time() // 30))})
check("Après réinitialisation : l'ancien secret ne permet plus rien", old.status_code == 401, old.status_code)
with owner.connect() as c:
    au = c.execute(text("SELECT reason, actor_user_id FROM audit_events WHERE action='PLATFORM_USER_MFA_RESET' AND entity_id=:u ORDER BY occurred_at DESC LIMIT 1"), {"u": acc["id"]}).mappings().first()
check("Réinitialisation auditée avec auteur et motif", au and au["reason"] == reason and str(au["actor_user_id"]) == mgr_id)
detail = mgr.get(f"platform/team/users/{acc['id']}").json()
check("Fiche équipe : statut MFA visible, sans secret ni code", detail["mfa"]["enrolled"] is False and "secret" not in json.dumps(detail))

# ---------- 9. password change keeps the factor; deactivation; school accounts untouched ----------
pw = new_account("c")
c_pw = login(pw["email"], pw["password"], "PLATFORM")  # enrols through the public API (common.complete_login)
newp = secrets.token_urlsafe(18)
ch = post(c_pw, "auth/platform/password", {"current_password": pw["password"], "new_password": newp})
check("Changement de mot de passe : toutes les sessions coupées", ch.status_code == 200 and c_pw.get("platform/team/me").status_code == 401, ch.status_code)
d = raw_login(pw["email"], newp).json()
check("Après changement de mot de passe : le facteur est conservé (code demandé, pas de ré-enrôlement)", d.get("mfa_required") is True and d.get("mfa_enrollment_required") is False)
with owner.begin() as c:
    c.execute(text("UPDATE users SET active=false WHERE id=:u"), {"u": pw["id"]})
check("Compte désactivé entre le mot de passe et le code : étape refusée", mfa("verify", {"mfa_token": d["mfa_token"], "code": "123456"}).status_code == 401)
schoolA = ensure_school("A", ("ADMIN_SYSTEME_ECOLE",))
sa = ensure_user(schoolA, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
sl = raw_login(sa["email"], sa["password"])
check("Compte école : connexion directe, aucun second facteur demandé", sl.status_code == 200 and "access_token" in sl.json() and "mfa_token" not in sl.json(), sl.status_code)
sc = bearer(sl.json()["access_token"])
check("Compte école : API MFA plateforme inaccessible", sc.get("auth/platform/mfa").status_code in (401, 403))

# ---------- 9b. operator recovery (last Manager without phone nor recovery codes) ----------
import subprocess  # noqa: E402
SCRIPT = str(Path(__file__).resolve().parents[2] / "backend" / "scripts" / "reset_platform_mfa.py")


def operator(*args):
    return subprocess.run([sys.executable, SCRIPT, *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)


why = f"Téléphone et codes de secours perdus, identité vérifiée en personne ({run})"
bad = operator("--email", lock["email"], "--operator", "Opérateur recette", "--reason", why, "--confirm", "autre@example.test")
check("Procédure opérateur : confirmation erronée → refus, rien n'est modifié", bad.returncode == 2, bad.returncode)
school_try = operator("--email", sa["email"], "--operator", "Opérateur recette", "--reason", why, "--confirm", sa["email"])
check("Procédure opérateur : compte école refusé (pas de second facteur)", school_try.returncode == 3, school_try.returncode)
okop = operator("--email", lock["email"], "--operator", "Opérateur recette", "--reason", why, "--confirm", lock["email"])
check("Procédure opérateur : réinitialisation du facteur (identifiants propriétaire de la base requis)", okop.returncode == 0, (okop.stderr or okop.stdout)[-200:])
with owner.connect() as c:
    au = c.execute(text("SELECT reason, new_json, actor_user_id, source FROM audit_events WHERE action='PLATFORM_USER_MFA_RESET_BY_OPERATOR' AND entity_id=:u ORDER BY occurred_at DESC LIMIT 1"),
                   {"u": lock["id"]}).mappings().first()
    active = c.execute(text("SELECT count(*) FROM user_mfa_factors WHERE user_id=:u AND status='ACTIVE'"), {"u": lock["id"]}).scalar_one()
check("Procédure opérateur auditée : opérateur nommé, motif, source SYSTEM", au and au["reason"] == why and au["new_json"]["operator"] == "Opérateur recette" and au["source"] == "SYSTEM")
check("Procédure opérateur : aucun accès donné (facteur retiré, ré-enrôlement exigé à la connexion)", active == 0)

# ---------- 10. secrets never leak (audit, logs) ----------
pw_state = state[MFA_STATE].get(pw["email"], {})
needles = [secret, s2, *codes, *new_codes, pw_state.get("secret", "x" * 32), *pw_state.get("recovery_codes", [])]
with owner.connect() as c:
    leaked = c.execute(text("SELECT count(*) FROM audit_events WHERE occurred_at>now()-interval '1 hour' AND (" + " OR ".join(
        f"coalesce(new_json::text,'') LIKE :n{i} OR coalesce(old_json::text,'') LIKE :n{i} OR coalesce(reason,'') LIKE :n{i}" for i in range(len(needles))) + ")"),
        {f"n{i}": f"%{n}%" for i, n in enumerate(needles)}).scalar_one()
check("Aucun secret TOTP ni code de secours dans l'audit", leaked == 0, leaked)
logs = Path(__file__).resolve().parents[2] / ".local" / "logs"
found = [p.name for p in logs.glob("*.log") if any(n in p.read_text(encoding="utf-8", errors="ignore") for n in needles)]
check("Aucun secret TOTP ni code de secours dans les journaux du serveur", not found, found)
with owner.connect() as c:
    kinds = set(c.execute(text("SELECT action FROM audit_events WHERE entity_id IN (:a,:b) AND action LIKE '%MFA%'"), {"a": acc["id"], "b": lock["id"]}).scalars())
check("Événements audités : enrôlement, vérification, code de secours, régénération, échec, réinitialisation",
      {"MFA_ENROLLMENT_STARTED", "MFA_ENROLLED", "MFA_VERIFIED", "MFA_RECOVERY_CODE_USED", "MFA_RECOVERY_CODES_REGENERATED", "MFA_FAILED", "PLATFORM_USER_MFA_RESET"} <= kinds, sorted(kinds))

# ---------- 11. Manager système itself ----------
m = httpx.post(BASE + "/auth/login", json={"email": mgr_email, "password": os.environ["EDUSYNC_PLATFORM_ADMIN_PASSWORD"]}, timeout=30).json()
check("Manager système : second facteur exigé à chaque nouvelle connexion", m.get("mfa_required") is True and "access_token" not in m)

# A fresh, not yet enrolled platform account for the UI journey (n1_journey.mjs enrols it through the screens).
fx["ui"] = {k: v for k, v in new_account("ui").items() if k in ("email", "password", "id")}
save()

out = Path(__file__).with_name("mfa-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
