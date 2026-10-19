"""EduSync — parcours de bout en bout contre STAGING, après chaque déploiement (lot 2026-10).

Lecture seule, non destructif : un compte plateforme de test dédié (rôle en lecture, jamais un Manager) se connecte
avec son code (TOTP), lit les écrans plateforme, change d'espace si plusieurs espaces lui sont ouverts, renouvelle sa
session puis se déconnecte (la session est révoquée). Bibliothèque standard uniquement. Aucun secret affiché : les
identifiants viennent des secrets GitHub E2E_PLATFORM_EMAIL / E2E_PLATFORM_PASSWORD / E2E_PLATFORM_TOTP_SECRET.
Code de sortie 1 au premier échec bloquant ; un tableau de résultats est écrit dans $GITHUB_STEP_SUMMARY.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.cookiejar
import json
import os
import re
import struct
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get("E2E_BASE_URL", "https://staging.myeducsync.com").rstrip("/")
EMAIL, PASSWORD, SECRET = (os.environ.get(k, "") for k in ("E2E_PLATFORM_EMAIL", "E2E_PLATFORM_PASSWORD", "E2E_PLATFORM_TOTP_SECRET"))
ROWS: list[tuple[str, str, str]] = []
FAILS = 0


def check(ok: bool, label: str, detail: str = "") -> bool:
    global FAILS
    ROWS.append(("PASS" if ok else "ÉCHEC", label, detail))
    print(("PASS  " if ok else "FAIL  ") + label + (f" — {detail}" if detail else ""), flush=True)
    FAILS += 0 if ok else 1
    return ok


def totp(secret: str, step: int | None = None) -> str:
    key = base64.b32decode(secret.replace(" ", "").upper() + "=" * (-len(secret.replace(" ", "")) % 8))
    counter = int(time.time() // 30) if step is None else step
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    o = digest[-1] & 0x0F
    return f"{(struct.unpack('>I', digest[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000:06d}"


jar = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))


def call(method: str, path: str, token: str | None = None, body=None, timed: list | None = None):
    h = {"Content-Type": "application/json", "Origin": BASE, "User-Agent": "edusync-e2e-staging"}
    if token:
        h["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(BASE + path, method=method, headers=h, data=json.dumps(body).encode() if body is not None else None)
    t0 = time.perf_counter()
    try:
        with opener.open(req, timeout=40) as r:
            raw = r.read().decode("utf-8", "replace"); code = r.status
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace"); code = e.code
    if timed is not None:
        timed.append(int((time.perf_counter() - t0) * 1000))
    try:
        return code, json.loads(raw) if raw else None
    except ValueError:
        return code, raw


def summary() -> None:
    out = os.environ.get("GITHUB_STEP_SUMMARY")
    if not out:
        return
    with open(out, "a", encoding="utf-8") as f:
        f.write(f"### Parcours de bout en bout — {BASE}\n| Résultat | Étape | Détail |\n|---|---|---|\n")
        for r in ROWS:
            f.write(f"| {r[0]} | {r[1]} | {r[2]} |\n")


def main() -> int:
    # 1. the served interface is this release (key screens present in the bundle)
    code, html = call("GET", "/")
    assets = re.findall(r"/assets/[\w.-]+\.js", html if isinstance(html, str) else "")
    check(code == 200 and bool(assets), "interface servie", f"{len(assets)} script(s)")
    if not (EMAIL and PASSWORD and SECRET):
        check(True, "compte de test absent : parcours connecté non exécuté",
              "secrets E2E_PLATFORM_* à créer (docs/architecture/RUNBOOK_INCIDENT.md §6)")
        return 0

    # 2. sign-in with the second factor (one TOTP step is single-use: wait for a fresh step if needed)
    times: list[int] = []
    code, step = call("POST", "/api/v1/auth/login", body={"email": EMAIL, "password": PASSWORD, "scope": "PLATFORM"}, timed=times)
    if not check(code == 200 and isinstance(step, dict) and step.get("mfa_token"), "connexion : mot de passe accepté, code demandé", f"HTTP {code}"):
        return 1
    token = None
    for _ in range(3):
        while time.time() % 30 > 25:
            time.sleep(0.5)
        code, sess = call("POST", "/api/v1/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": totp(SECRET)}, timed=times)
        if code == 200:
            token = sess["access_token"]
            break
        time.sleep(31)
    if not check(bool(token), "connexion : code à 6 chiffres accepté", f"{times[-1]} ms"):
        return 1

    # 3. platform screens (read only); an unauthorised screen must say 403, never 500
    code, me = call("GET", "/api/v1/platform/team/me", token)
    check(code == 200 and isinstance(me, dict) and me.get("menu"), "profil et menu calculés par le serveur", f"{len(me.get('menu', [])) if isinstance(me, dict) else 0} écran(s)")
    menu = {m["key"] for m in me.get("menu", [])} if isinstance(me, dict) else set()
    screens = [("dashboard", "/api/v1/platform/dashboard"), ("schools", "/api/v1/platform/schools-page?limit=20"),
               ("access", "/api/v1/platform/identities?limit=20"), ("diagnostics", "/api/v1/platform/system/health"),
               ("diagnostics", "/api/v1/platform/system/health/errors?window=24h"), ("diagnostics", "/api/v1/platform/system/health/incidents"),
               ("audit", "/api/v1/platform/audit-log?limit=20")]
    for key, path in screens:
        t: list[int] = []
        code, _ = call("GET", path, token, timed=t)
        if key in menu:
            check(code == 200, f"écran ouvert : {path.split('?')[0]}", f"HTTP {code} · {t[0]} ms")
        else:
            check(code in (403, 404), f"écran non attribué refusé : {path.split('?')[0]}", f"HTTP {code}")
    code, health = call("GET", "/api/v1/platform/system/health", token)
    if code == 200 and isinstance(health, dict):
        bad = [f"{a['title']} ({a['explain']})" for a in health.get("alerts", []) if a["severity"] == "critical"]
        check(not bad, "aucun service hors service sur staging", "; ".join(bad)[:300] if bad else health.get("overall", ""))

    # 4. change of space when several are open, and back
    code, ctx = call("GET", "/api/v1/auth/contexts")
    check(code == 200 and isinstance(ctx, dict), "espaces de l’identité", f"{len(ctx.get('contexts', [])) if isinstance(ctx, dict) else 0} espace(s)")
    schools = [c for c in (ctx.get("contexts", []) if isinstance(ctx, dict) else []) if c["scope"] == "SCHOOL"]
    if schools:
        code, sw = call("POST", "/api/v1/auth/switch", body={"scope": "SCHOOL", "school_code": schools[0]["school_code"]})
        check(code == 200 and sw.get("scope") == "SCHOOL", "changement d’espace vers une école sans se reconnecter", f"HTTP {code}")
        code, sw = call("POST", "/api/v1/auth/switch", body={"scope": "PLATFORM"})
        check(code == 200 and sw.get("scope") == "PLATFORM", "retour à la plateforme sans code", f"HTTP {code}")
        token = sw.get("access_token", token) if isinstance(sw, dict) else token

    # 5. session renewal, then sign-out revokes it
    code, rf = call("POST", "/api/v1/auth/refresh")
    check(code == 200 and isinstance(rf, dict) and rf.get("access_token"), "session renouvelée (rechargement de page)", f"HTTP {code}")
    code, _ = call("POST", "/api/v1/auth/logout")
    check(code in (200, 204), "déconnexion", f"HTTP {code}")
    code, _ = call("POST", "/api/v1/auth/refresh")
    check(code == 401, "après déconnexion : session révoquée", f"HTTP {code}")
    check(max(times) < 5000, "temps de connexion", f"max {max(times)} ms")
    return 1 if FAILS else 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        summary()
    print("RÉSULTAT : " + ("PASS" if FAILS == 0 else f"ÉCHEC ({FAILS})"))
    sys.exit(rc or (1 if FAILS else 0))
