"""Pre-staging — real Docker stack in staging mode (docker compose -p edusync-smoke, env file .local/staging-smoke.env).

Checks, through nginx exactly as a browser would (Host: staging.edusync.localhost):
  services up, migrator OK; API safety checks active (and a weakened configuration refused); SeaweedFS document
  storage (put/get/checksum); first Manager Système through the one-time setup token, then mandatory TOTP; Secure
  session cookie; import body > 1 MB reaches the API (nginx limit 11 MB, > 11 MB refused by nginx); SSE stream kept
  open beyond nginx's former 60 s cut; a real backup, restored into an isolated database, row counts and SHA-256
  checked; the backup status file read by the platform health screen.
Secrets and generated passwords stay in .local/ and are never printed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import struct
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / ".local" / "staging-smoke.env"
ACCOUNTS = ROOT / ".local" / "staging-smoke-accounts.json"
OUT = Path(__file__).with_name("staging-stack-live.json")
HOST = "staging.edusync.localhost"
BASE = "http://127.0.0.1:8080"
DC = ["docker", "compose", "--env-file", str(ENV_FILE), "-p", "edusync-smoke"]
ENV = dict(line.split("=", 1) for line in ENV_FILE.read_text(encoding="utf-8").splitlines() if "=" in line and not line.startswith("#"))
results: list[dict] = []


def check(name: str, ok: bool, detail="") -> bool:
    results.append({"check": name, "result": "PASS" if ok else "FAIL", "detail": str(detail)[:300]})
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {str(detail)[:200]}" if detail != "" else ""), flush=True)
    return ok


def dc(*args: str, timeout: int = 600) -> subprocess.CompletedProcess:
    return subprocess.run([*DC, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)


def http(method: str, path: str, **kw) -> httpx.Response:
    headers = {"Host": HOST, **kw.pop("headers", {})}
    return httpx.request(method, BASE + path, headers=headers, timeout=kw.pop("timeout", 30), **kw)


def totp(secret_b32: str, step: int) -> str:
    key = base64.b32decode(secret_b32.upper() + "=" * (-len(secret_b32) % 8))
    d = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    o = d[-1] & 0x0F
    return str((struct.unpack(">I", d[o:o + 4])[0] & 0x7FFFFFFF) % 1_000_000).zfill(6)


# ---------------------------------------------------------------- 1. services
ps = json.loads("[" + ",".join(x for x in dc("ps", "-a", "--format", "json").stdout.splitlines() if x.strip()) + "]")
state = {p["Service"]: (p["State"], p.get("Health", ""), p.get("ExitCode")) for p in ps}
expected = ("postgres", "redis", "object-storage", "backend", "outbox-worker", "communications-worker", "frontend", "backup")
check("Pile démarrée : 8 services en fonctionnement", all(state.get(s, ("",))[0] == "running" for s in expected), state)
check("Migrateur terminé avec succès (code 0)", state.get("migrator", ("", "", None))[0] == "exited" and state["migrator"][2] == 0, state.get("migrator"))
check("API saine (healthcheck Docker)", state.get("backend", ("", ""))[1] == "healthy", state.get("backend"))
mig = dc("logs", "migrator").stdout
check("Provisionnement complet de la base vierge", "POINT-4A database provisioning: PASS" in mig, mig.strip().splitlines()[-1:] if mig.strip() else "")

# ---------------------------------------------------------------- 2. safety checks
r = dc("exec", "-T", "backend", "python", "-c",
       "from edusync.bootstrap.settings import Settings;s=Settings();s.assert_runtime_safe();print(s.env, s.object_storage_backend)")
check("Contrôles de sécurité actifs en staging : configuration réelle acceptée", r.returncode == 0 and r.stdout.strip().startswith("staging"), r.stdout.strip() or r.stderr[-200:])
weak = {"EDUSYNC_CORS_ORIGINS": "http://staging.edusync.localhost", "EDUSYNC_JWT_SECRET": "dev-only-change-me-dev-only-change-me",
        "EDUSYNC_PUSH_PROVIDER": "mock", "EDUSYNC_MFA_ENCRYPTION_KEY": ""}
refused = []
for var, val in weak.items():
    rr = dc("exec", "-T", "-e", f"{var}={val}", "backend", "python", "-c",
            "from edusync.bootstrap.settings import Settings;Settings().assert_runtime_safe()")
    refused.append((var, rr.returncode != 0 and "RuntimeError" in rr.stderr))
check("Configuration affaiblie refusée en staging (CORS HTTP, secret de dev, push simulé, clé MFA absente)", all(x for _, x in refused), refused)

# ---------------------------------------------------------------- 3. document storage (SeaweedFS)
blob = secrets.token_bytes(4096)
digest = hashlib.sha256(blob).hexdigest()
code = ("import sys,hashlib;from edusync.bootstrap.settings import Settings;from edusync.shared.infrastructure.object_storage import build_object_storage;"
        "s=build_object_storage(Settings());s.ensure_bucket();d=sys.stdin.buffer.read();s.put('smoke/probe.bin',d,content_type='application/octet-stream');"
        "g=s.get('smoke/probe.bin');print(type(s).__name__,hashlib.sha256(g).hexdigest())")
p = subprocess.run([*DC, "exec", "-T", "backend", "python", "-c", code], cwd=ROOT, input=blob, capture_output=True, timeout=120)
out = p.stdout.decode(errors="replace").split()
check("SeaweedFS : bucket privé, écriture puis relecture identique (SHA-256)", p.returncode == 0 and out[:1] == ["S3CompatibleObjectStorage"] and out[-1:] == [digest],
      out or p.stderr.decode(errors="replace")[-200:])
anon = dc("exec", "-T", "backend", "python", "-c",
          "import httpx;print(httpx.get('http://object-storage:8333/edusync-documents/smoke/probe.bin').status_code)")
check("Stockage : lecture anonyme refusée (bucket privé)", anon.stdout.strip() in ("403", "401"), anon.stdout.strip())

# ---------------------------------------------------------------- 4. first Manager Système + MFA
st = http("GET", "/api/v1/setup/status").json()
check("Installation vierge : création du premier manager disponible, jeton exigé",
      st.get("setup_required") is True and st.get("setup_available") is True and st.get("token_required") is True, st)
acc = {"email": "manager@staging.edusync.localhost", "password": secrets.token_urlsafe(18) + "Aa1!", "full_name": "Manager Recette Staging"}
no_tok = http("POST", "/api/v1/setup/first-manager", json={**acc})
bad_tok = http("POST", "/api/v1/setup/first-manager", json={**acc, "setup_token": "faux-" + secrets.token_hex(8)})
check("Premier manager : sans jeton ou avec un faux jeton → refusé", no_tok.status_code in (401, 403) and bad_tok.status_code in (401, 403), (no_tok.status_code, bad_tok.status_code))
ok_tok = http("POST", "/api/v1/setup/first-manager", json={**acc, "setup_token": ENV["EDUSYNC_SETUP_TOKEN"]})
check("Premier manager créé avec le jeton de setup à usage unique", ok_tok.status_code == 201, ok_tok.status_code)
ACCOUNTS.write_text(json.dumps({"manager": acc}, indent=1), encoding="utf-8")
again = http("POST", "/api/v1/setup/first-manager", json={**acc, "email": "autre@staging.edusync.localhost", "setup_token": ENV["EDUSYNC_SETUP_TOKEN"]})
check("Jeton de setup inutilisable une seconde fois (installation terminée)", again.status_code in (403, 409, 410), again.status_code)

lg = http("POST", "/api/v1/auth/login", json={"email": acc["email"], "password": acc["password"]}).json()
check("Connexion plateforme : pas de session avant le second facteur, enrôlement TOTP obligatoire",
      "access_token" not in lg and lg.get("mfa_enrollment_required") is True, sorted(lg))
es = http("POST", "/api/v1/auth/mfa/enroll/start", json={"mfa_token": lg["mfa_token"]}).json()
secret = es["secret"]
step = int(time.time() // 30)
cf = http("POST", "/api/v1/auth/mfa/enroll/confirm", json={"mfa_token": lg["mfa_token"], "code": totp(secret, step)})
cd = cf.json()
token = cd.get("access_token")
acc_state = {"manager": acc, "totp_secret": secret, "last_step": step}
ACCOUNTS.write_text(json.dumps(acc_state, indent=1), encoding="utf-8")
check("MFA activée : session ouverte après confirmation du code TOTP, codes de secours fournis", cf.status_code == 200 and bool(token) and len(cd.get("recovery_codes", [])) == 10, cf.status_code)
cookie = cf.headers.get("set-cookie", "")
check("Cookie de session : HttpOnly, SameSite=Lax et Secure en staging", "httponly" in cookie.lower() and "samesite=lax" in cookie.lower() and "secure" in cookie.lower(),
      [x.strip().split("=")[0] for x in cookie.split(";")][1:])
auth = {"Authorization": f"Bearer {token}"}

# ---------------------------------------------------------------- 5. import body through nginx
big = b"PK" + secrets.token_bytes(2 * 1024 * 1024)
for route in ("/api/v1/import/students/analyze", "/api/v1/import/students/date-repair/preview"):
    r2 = http("POST", route, content=big, headers={**auth, "Content-Type": "application/octet-stream"}, timeout=60)
    # A platform token is not a school actor: the API answers 401/403 itself once nginx and the size guard let the body through.
    check(f"Import de 2 Mio ({route.rsplit('/import/', 1)[1]}) : franchit nginx et la garde de taille, réponse de l'API",
          r2.status_code in (401, 403) and r2.headers.get("content-type", "").startswith("application/json"), (r2.status_code, r2.text[:120]))
huge = b"PK" + secrets.token_bytes(12 * 1024 * 1024)
r12 = http("POST", "/api/v1/import/students/date-repair/preview", content=huge, headers={**auth, "Content-Type": "application/octet-stream"}, timeout=120)
check("Corps de 12 Mio : refusé par nginx (413) au-delà de la limite de 11 Mo", r12.status_code == 413, r12.status_code)

# ---------------------------------------------------------------- 6. SSE stream through nginx
events, t0, closed_early = [], time.time(), False
try:
    with httpx.stream("GET", BASE + "/api/v1/platform/inbox/stream", headers={"Host": HOST, **auth}, timeout=httpx.Timeout(10, read=40)) as s:
        ctype = s.headers.get("content-type", "")
        for chunk in s.iter_text():
            for line in chunk.splitlines():
                if line.startswith("event:") or line.startswith(":"):
                    events.append((round(time.time() - t0), line.strip()))
            if time.time() - t0 > 75:
                break
except httpx.HTTPError as exc:
    closed_early = time.time() - t0 < 75
    events.append(("err", type(exc).__name__))
late = [e for e in events if isinstance(e[0], int) and e[0] >= 61]
check("Flux SSE via nginx : type text/event-stream, événement « ready »", "text/event-stream" in ctype and any("ready" in e[1] for e in events), events[:2])
check("Flux SSE maintenu au-delà de 60 s (ancienne coupure nginx) : battements reçus après 61 s", not closed_early and bool(late), (len(events), late[:2]))

# ---------------------------------------------------------------- 7. real backup, isolated restore, counts and checksums
bk = dc("exec", "-T", "backup", "sh", "/usr/local/bin/edusync-backup", "once", timeout=900)
check("Sauvegarde réelle exécutée (pg_dump + documents + restauration isolée)", bk.returncode == 0 and "PASS sauvegarde" in bk.stdout, (bk.stdout + bk.stderr).strip()[-300:])
last = json.loads(dc("exec", "-T", "backup", "cat", "/backup-status/last.json").stdout or "{}")
ts = last.get("detail", "")
check("Fichier d'état : ok=true, restore_verified=true", last.get("ok") is True and last.get("restore_verified") is True, last)
sums = dc("exec", "-T", "backup", "sh", "-c", f"cd /backups/{ts} && sha256sum -c SHA256SUMS >/dev/null && echo CHECKSUMS_OK && wc -l < SHA256SUMS")
check("Checksums SHA-256 de la sauvegarde vérifiés", "CHECKSUMS_OK" in sums.stdout, sums.stdout.strip() or sums.stderr[-200:])
cmp = dc("exec", "-T", "backup", "sh", "-c", f"cd /backups/{ts} && paste -d' ' counts.before counts.restored counts.after")
rows = [line.split() for line in cmp.stdout.strip().splitlines()]
okc = all(len(x) == 3 and x[0].split("=")[0] == x[1].split("=")[0] and int(x[0].split("=")[1]) <= int(x[1].split("=")[1]) <= int(x[2].split("=")[1]) for x in rows)
check("Comptes de lignes : base restaurée isolée encadrée par avant/après sauvegarde (12 tables)", len(rows) == 12 and okc,
      {x[1].split("=")[0]: x[1].split("=")[1] for x in rows if len(x) == 3})
obj = dc("exec", "-T", "backup", "sh", "-c", f"sha256sum /backups/{ts}/objects/smoke/probe.bin | cut -d' ' -f1")
check("Document de test présent dans la sauvegarde avec le même SHA-256", obj.stdout.strip() == digest, obj.stdout.strip()[:16])
gone = dc("exec", "-T", "postgres", "psql", "-U", ENV["POSTGRES_OWNER_USER"], "-d", "postgres", "-tAc",
          "SELECT count(*) FROM pg_database WHERE datname='edusync_restore_check'")
check("Base de vérification isolée supprimée après contrôle", gone.stdout.strip() == "0", gone.stdout.strip())

# ---------------------------------------------------------------- 8. platform health reads the backup status
health = http("GET", "/api/v1/platform/system/health", headers=auth)
comp = {c["key"]: c for c in health.json().get("components", [])} if health.status_code == 200 else {}
check("Écran de santé : base, Redis et stockage OK", all(comp.get(k, {}).get("state") == "OK" for k in ("database", "redis", "storage")),
      {k: comp.get(k, {}).get("state") for k in ("database", "redis", "storage")} or health.status_code)
check("Écran de santé : dernière sauvegarde OK, restauration vérifiée", comp.get("backup", {}).get("state") == "OK" and "restauration vérifiée" in comp.get("backup", {}).get("detail", ""),
      comp.get("backup", {}).get("detail"))

passed = sum(r["result"] == "PASS" for r in results)
OUT.write_text(json.dumps({"stack": "docker compose -p edusync-smoke (EDUSYNC_ENV=staging)", "checks": results,
                           "summary": f"{passed}/{len(results)}"}, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"== {passed}/{len(results)} {'PASS' if passed == len(results) else 'FAIL'} -> {OUT.name}")
sys.exit(0 if passed == len(results) else 1)
