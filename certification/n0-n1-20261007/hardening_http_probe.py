"""Live probe — hardening D (HTTP security) and E (rate limiting) on the running local stack."""
import json
import os
import sys
from pathlib import Path
from uuid import uuid4

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, platform, state  # noqa: E402

APP = "http://localhost:5180"
results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


mult = float(os.environ.get("EDUSYNC_RATE_LIMIT_MULTIPLIER", "1") or 1)

# ---------------- D. HTTP security ----------------
h = httpx.get(APP + "/", timeout=30).headers
csp = h.get("content-security-policy", "")
check("Interface : CSP stricte (script-src 'self', pas de unsafe-eval ni d'inline script)", "script-src 'self'" in csp and "unsafe-eval" not in csp and "script-src 'self' 'unsafe-inline'" not in csp, csp[:120])
check("Interface : frame-ancestors 'none' + X-Frame-Options DENY", "frame-ancestors 'none'" in csp and h.get("x-frame-options") == "DENY")
check("Interface : nosniff, Referrer-Policy, Permissions-Policy, COOP", h.get("x-content-type-options") == "nosniff" and h.get("referrer-policy") == "strict-origin-when-cross-origin" and "camera=()" in h.get("permissions-policy", "") and h.get("cross-origin-opener-policy") == "same-origin")
check("Interface : HTML revalidé à chaque visite (mise à jour garantie)", "no-cache" in h.get("cache-control", ""))
check("Interface : aucun en-tête serveur révélateur", "server" not in {k.lower() for k in h.keys()} or "vite" not in h.get("server", "").lower(), h.get("server"))
mgr = platform()
api_h = mgr.get("platform/team/me").headers
check("API authentifiée : réponse non mise en cache partagé", any(x in api_h.get("cache-control", "") for x in ("no-store", "private")), api_h.get("cache-control"))
check("API : CSP, nosniff, DENY, pas d'en-tête Server", "frame-ancestors 'none'" in api_h.get("content-security-policy", "") and api_h.get("x-content-type-options") == "nosniff" and "server" not in {k.lower() for k in api_h.keys()})
pre = httpx.options(BASE + "/auth/login", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"}, timeout=30)
check("CORS : origine étrangère non autorisée", pre.headers.get("access-control-allow-origin") not in ("*", "https://evil.example"), pre.headers.get("access-control-allow-origin"))
lg = httpx.post(BASE + "/auth/login", json={"email": os.environ["EDUSYNC_PLATFORM_ADMIN_EMAIL"], "password": os.environ["EDUSYNC_PLATFORM_ADMIN_PASSWORD"]}, timeout=30)
sc = lg.headers.get("set-cookie", "")
check("Cookie de session : HttpOnly, SameSite=Lax, chemin restreint", "HttpOnly" in sc and "SameSite=lax" in sc and "Path=/api/v1/auth" in sc)
check("Jeton d'accès jamais dans l'URL ni dans un cookie lisible par script", "access_token" not in sc and "token=" not in str(lg.url))
check("HSTS : non émis en HTTP local (HTTPS public : BLOCKED_EXTERNAL)", "strict-transport-security" not in {k.lower() for k in api_h.keys()})

# ---------------- E. Rate limiting ----------------
u2 = state["N1_TEAM"]["u2"]
lr = httpx.post(BASE + "/auth/login", json={"email": u2["email"], "password": u2["password"]}, timeout=30)
c2 = httpx.Client(base_url=BASE + "/", headers={"Authorization": "Bearer " + lr.json()["access_token"]}, timeout=30)
limit = int(30 * mult)
codes = [c2.post("platform/schools", json={"name": "Tentative", "code": f"RL{i}"}, headers={"Idempotency-Key": str(uuid4())}).status_code for i in range(limit + 2)]
first_429 = codes.index(429) if 429 in codes else None
check(f"Création d'école : limitée à {limit}/h par compte (puis 429)", first_429 == limit and all(c == 403 for c in codes[:limit]), f"premier 429 à l'essai {first_429}")
r = c2.post("platform/schools", json={"name": "x", "code": "RLX"}, headers={"Idempotency-Key": str(uuid4())})
check("429 : Retry-After et message en français", r.status_code == 429 and int(r.headers.get("retry-after", "0")) > 0 and "Réessayez" in r.json()["detail"])
ok = mgr.post("platform/schools", json={"name": "x"}, headers={"Idempotency-Key": str(uuid4())})
check("Compteur par compte : un autre compte n'est pas bloqué", ok.status_code == 422, ok.status_code)
plimit = int(10 * mult)
codes = [c2.post("auth/platform/password", json={"current_password": "mauvais", "new_password": "x" * 14}, headers={"Idempotency-Key": str(uuid4())}).status_code for _ in range(plimit + 1)]
check(f"Changement de mot de passe : limité à {plimit}/h (anti-devinette)", codes[-1] == 429 and codes.count(400) == plimit, f"{codes.count(400)} refus puis {codes[-1]}")
bad = httpx.post(BASE + "/auth/login", json={"email": f"brute-{uuid4().hex[:6]}@example.test", "password": "x"}, timeout=30)
attempts = [httpx.post(BASE + "/auth/login", json={"email": "brute-force-n1@example.test", "password": f"x{i}"}, timeout=30).status_code for i in range(9)]
check("Connexion : verrouillage après tentatives répétées (garde dédiée)", 429 in attempts, attempts)

out = Path(__file__).with_name("hardening-http-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
