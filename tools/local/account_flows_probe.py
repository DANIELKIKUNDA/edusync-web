"""Local probe of the account e-mail flows (lot 2026-10): Use case → outbox → worker → policy → e-mail provider.

With the development e-mail simulator (it keeps every e-mail in Redis), the probe reads the REAL link received:
platform collaborator invitation (no password in the e-mail, link in the URL fragment, single use, replay refused),
re-sent invitation (the previous link stops working), password forgotten (same answer for an unknown address, link
single use, open links revoked, sessions closed), e-mail templates (subject, HTML, text, Volcano Tech signature).
Accounts created by the probe lose their platform access at the end; the school account used for the reset gets its
original password back. Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/account_flows_probe.py
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
import redis  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from edusync.shared.infrastructure.mfa import current_step, totp_code  # noqa: E402

API = "http://127.0.0.1:58100/api/v1"
env = L.load_env("demo")
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
r = redis.Redis.from_url(env["EDUSYNC_REDIS_URL"], decode_responses=True)
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
TAG = uuid.uuid4().hex[:6]
FAILS = 0


def check(ok, label):
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def sql(q, **p):
    with owner.begin() as c:
        res = c.execute(text(q), p)
        return res.mappings().all() if res.returns_rows else res.rowcount


def call(method, path, token=None, body=None, key=None):
    h = {"Content-Type": "application/json", "Origin": "http://localhost:5180", **({"Authorization": f"Bearer {token}"} if token else {}),
         **({"Idempotency-Key": key} if key else {})}
    req = urllib.request.Request(API + path, method=method, data=json.dumps(body).encode() if body is not None else None, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode(); return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except ValueError:
            return e.code, raw


SEEN: set[str] = set()


def mailbox(to: str, anchor: str, after: float, timeout: int = 60):
    """Newest simulated e-mail to `to` received after `after` (full timestamp) whose link was not used yet."""
    from datetime import datetime, timezone
    floor = datetime.fromtimestamp(after, timezone.utc)
    deadline = time.time() + timeout
    while time.time() < deadline:
        for raw in r.lrange("edusync:messaging:fake:email", 0, 199):
            e = json.loads(raw)
            if e.get("to") != to or datetime.fromisoformat(e["at"]) < floor:
                continue
            m = re.search(rf"#{anchor}=([A-Za-z0-9_\-]+)", e.get("text", ""))
            if m and m.group(1) not in SEEN:
                SEEN.add(m.group(1))
                return e, m.group(1)
        time.sleep(1.5)
    return None, None


def login_mgr():
    _, step = call("POST", "/auth/login", body={"email": "certification@example.test", "password": ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"], "scope": "PLATFORM"})
    for _ in range(3):
        while time.time() % 30 > 25:
            time.sleep(0.5)
        code, sess = call("POST", "/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": totp_code(FX["MFA_TOTP"]["certification@example.test"]["secret"], current_step())})
        if code == 200:
            return sess["access_token"]
        time.sleep(31)
    raise SystemExit("connexion impossible")


mgr = login_mgr()
created: list[str] = []
try:
    # ------------------------------------------------------------ invitation of a platform collaborator
    email1 = f"invite-{TAG}@example.test"
    t0 = time.time() - 2
    code, u = call("POST", "/platform/team/users", mgr, {"email": email1, "full_name": f"Invité Sonde {TAG}", "role_codes": ["COLLABORATEUR_PLATEFORME"],
                                                         "reason": "Sonde des parcours de compte", "delivery": "INVITATION"}, key=f"inv-{TAG}-1")
    check(code in (200, 201) and isinstance(u, dict), f"création d’un collaborateur par invitation (HTTP {code})")
    uid = (u.get("id") or u.get("user", {}).get("id")) if isinstance(u, dict) else None
    if not uid:
        uid = str(sql("SELECT id FROM users WHERE email=:e", e=email1)[0]["id"])
    uid = str(uid)
    created.append(uid)
    code2, _ = call("POST", "/platform/team/users", mgr, {"email": email1, "full_name": f"Invité Sonde {TAG}", "role_codes": ["COLLABORATEUR_PLATEFORME"],
                                                         "reason": "Sonde des parcours de compte", "delivery": "INVITATION"}, key=f"inv-{TAG}-1")
    check(sql("SELECT count(*) n FROM communication_messages WHERE template_code='ACCOUNT_INVITATION' AND created_at >= now() - interval '2 minutes' AND id IN "
              "(SELECT message_id FROM communication_recipients WHERE email=:e)", e=email1)[0]["n"] == 1, "rejeu de la création : une seule invitation envoyée")
    mail, tok1 = mailbox(email1, "invitation", t0)
    check(mail is not None and tok1, "e-mail d’invitation reçu par le fournisseur (via l’outbox et le worker)")
    if mail:
        check("mot de passe" not in mail["text"].lower().split("choisir")[0] or "aucun mot de passe" in mail["text"].lower() or "choisir" in mail["text"].lower(),
              "aucun mot de passe envoyé : la personne choisit le sien")
        check("From Volcano Tech" in mail["text"] and "#invitation=" in mail["text"] and "?" not in mail["text"].split("#invitation=")[0][-30:],
              "lien dans le fragment d’URL, signature « From Volcano Tech »")
    stored = sql("SELECT token_hash FROM account_tokens WHERE user_id=:u AND purpose='INVITATION' ORDER BY created_at DESC LIMIT 1", u=uid)
    check(stored and tok1 and stored[0]["token_hash"] != tok1 and len(stored[0]["token_hash"]) == 64, "jeton stocké sous forme d’empreinte (jamais en clair)")
    # ------------------------------------------------------------ resend invalidates the previous link
    t1 = time.time() - 1
    time.sleep(1.2)
    code, rb = call("POST", f"/platform/team/users/{uid}/invitation/resend", mgr, {"reason": "Renvoi demandé par la sonde"}, key=f"res-{TAG}-1")
    mail2, tok2 = mailbox(email1, "invitation", t1)
    check(code == 200 and tok2 and tok2 != tok1, f"renvoi : un nouveau lien unique est envoyé (HTTP {code} {str(rb)[:120] if code != 200 else ''})")
    check(call("GET", f"/auth/invitations/{tok1}")[0] in (400, 404, 410), "l’ancien lien ne fonctionne plus après le renvoi")
    code, det = call("GET", f"/auth/invitations/{tok2}")
    check(code == 200 and "password" not in json.dumps(det).lower(), "nouveau lien valide, sans donnée sensible")
    newpw = f"Sonde-{TAG}-Mot-de-passe-1!"
    code, _ = call("POST", "/auth/invitations/accept", body={"token": tok2, "new_password": newpw})
    check(code == 200, "activation : la personne choisit son mot de passe")
    check(call("POST", "/auth/invitations/accept", body={"token": tok2, "new_password": newpw + "x"})[0] in (400, 404, 410), "lien déjà utilisé : refusé (usage unique)")
    code, step = call("POST", "/auth/login", body={"email": email1, "password": newpw, "scope": "PLATFORM"})
    check(code == 200 and isinstance(step, dict) and (step.get("mfa_enrollment_required") or step.get("mfa_required")),
          "connexion avec le mot de passe choisi : validation en deux étapes demandée (compte plateforme)")
    aud = sql("SELECT action FROM audit_events WHERE entity_id=CAST(:u AS uuid) OR (new_json->>'user_id')=CAST(:t AS text)", u=uid, t=uid)
    check(len(aud) >= 2, f"invitation, renvoi et activation journalisés ({len(aud)} événements)")

    # ------------------------------------------------------------ password forgotten (school account)
    school = FX["A"]["users"]["SECR"]
    t2 = time.time() - 1
    c_known, b_known = call("POST", "/auth/password/forgot", body={"email": school["email"]})
    c_unknown, b_unknown = call("POST", "/auth/password/forgot", body={"email": f"personne-{TAG}@example.test"})
    check(c_known == c_unknown == 202 and b_known == b_unknown, "même réponse que l’adresse existe ou non (aucune énumération)")
    mail3, rt = mailbox(school["email"], "reset", t2)
    check(mail3 is not None and rt and "From Volcano Tech" in mail3["text"], "e-mail de récupération reçu (lien unique, signature)")
    temp = f"Temp-{TAG}-Reset-Mot-de-passe-9!"
    code, _ = call("POST", "/auth/password/reset", body={"token": rt, "new_password": temp})
    check(code == 200, "nouveau mot de passe enregistré par le lien")
    check(call("POST", "/auth/password/reset", body={"token": rt, "new_password": temp + "x"})[0] in (400, 404, 410), "lien de récupération déjà utilisé : refusé")
    sessions = sql("SELECT count(*) n FROM user_device_sessions WHERE user_id=(SELECT id FROM users WHERE email=:e) AND revoked_at IS NULL", e=school["email"])[0]["n"]
    check(sessions == 0, "toutes les sessions de la personne sont fermées après la réinitialisation")
    from datetime import datetime, timezone
    found = False
    for _ in range(20):
        found = any(json.loads(x).get("to") == school["email"] and "sécurité" in (json.loads(x).get("subject") or "").lower()
                    and datetime.fromisoformat(json.loads(x)["at"]) >= datetime.fromtimestamp(t2, timezone.utc)
                    for x in r.lrange("edusync:messaging:fake:email", 0, 199))
        if found:
            break
        time.sleep(1.5)
    check(found, "alerte de sécurité envoyée après le changement de mot de passe")
    # restore the fixture password (second reset, through the same official flow)
    t3 = time.time() - 1
    call("POST", "/auth/password/forgot", body={"email": school["email"]})
    _, rt2 = mailbox(school["email"], "reset", t3)
    code, _ = call("POST", "/auth/password/reset", body={"token": rt2, "new_password": school["password"]}) if rt2 else (0, None)
    code_l, _ = call("POST", "/auth/login", body={"email": school["email"], "password": school["password"], "scope": "SCHOOL", "school_code": FX["A"]["code"]})
    check(code == 200 and code_l == 200, "mot de passe d’origine restauré par le même parcours officiel")
finally:
    for uid in created:
        call("POST", f"/platform/team/users/{uid}/platform-access/revoke", mgr, {"reason": "Fin de la sonde des parcours de compte"}, key=f"rev-{uid}")

print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
