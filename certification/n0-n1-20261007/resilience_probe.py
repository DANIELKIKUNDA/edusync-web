"""Live probe — hardening K (resilience): Redis, object storage, a worker and PostgreSQL are really stopped,
then restored with the launcher. Expected: no 500, 503 where a dependency is missing, no false success,
health reports the outage in plain words, clean recovery."""
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools" / "local"))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))
import edusync_local as L  # noqa: E402
from common import BASE, ensure_user, login, owner, platform, state  # noqa: E402
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.modules.documents.application import object_store  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def restore():
    owner.dispose()  # pooled connections do not survive a database restart
    subprocess.run([str(L.PY), str(L.ROOT / "tools" / "local" / "edusync_local.py"), "start", "--profile", "demo"], capture_output=True, timeout=900)


def health(client):
    r = client.get("platform/system/health")
    return r.status_code, ({c["key"]: c for c in r.json()["components"]} if r.status_code == 200 else {})


mgr = platform()
A = state["A"]
admin = ensure_user(A, "ADMIN", ("ADMIN_SYSTEME_ECOLE",))
check("Référence : tout fonctionne", mgr.get("platform/team/me").status_code == 200 and health(mgr)[1]["redis"]["state"] == "OK")

# ---------------- Redis ----------------
subprocess.run(["wsl.exe", "-d", L.WSL_DISTRO, "--", "sh", "-c", f"pkill -f 'redis-server.*:{L.PORTS['redis']}' || true"], capture_output=True)
time.sleep(2)
lg = httpx.post(BASE + "/auth/login", json={"email": admin["email"], "password": admin["password"]}, timeout=30)
check("Redis arrêté : la connexion reste possible (pas de 500)", lg.status_code == 200, lg.status_code)
st, comps = health(mgr)
check("Redis arrêté : santé « Hors service » en clair", st == 200 and comps["redis"]["state"] == "DOWN" and comps["redis"]["detail"] == "Injoignable", comps.get("redis"))
r = mgr.post("platform/team/roles", json={"code": "x", "label": "x", "capabilities": []}, headers={"Idempotency-Key": str(uuid4())})
check("Redis arrêté : opération limitée en débit traitée normalement (validation 422, pas 500)", r.status_code == 422, r.status_code)
restore()
check("Redis rétabli : santé OK", health(mgr)[1]["redis"]["state"] == "OK")

# ---------------- Object storage ----------------
with owner.connect() as c:
    doc = c.execute(text("SELECT id FROM generated_documents WHERE school_id=:s ORDER BY generated_at DESC LIMIT 1"), {"s": A["school_id"]}).scalar_one()
    uid = c.execute(text("SELECT id FROM users WHERE lower(email::text)=:e"), {"e": admin["email"].lower()}).scalar_one()
link, _ = object_store.sign_link(Settings(), document_id=str(doc), school_id=A["school_id"], user_id=str(uid))
ok_before = httpx.get(BASE + "/documents/open", params={"token": link}, timeout=30).status_code
L._kill("s3"); L._kill_port(L.PORTS["s3"])
time.sleep(2)
down = httpx.get(BASE + "/documents/open", params={"token": link}, timeout=60)
check("Stockage arrêté : document -> 503 avec message clair (pas 500)", ok_before == 200 and down.status_code == 503 and "indisponible" in down.json()["detail"], f"{ok_before} -> {down.status_code}")
check("Stockage arrêté : santé « Hors service »", health(mgr)[1]["storage"]["state"] == "DOWN")
restore()
check("Stockage rétabli : document de nouveau servi, intact", httpx.get(BASE + "/documents/open", params={"token": link}, timeout=60).status_code == 200)

# ---------------- Worker ----------------
L._kill("communications-worker")
time.sleep(70)
w = health(mgr)[1]["worker_communications"]
check("Worker SMS arrêté : santé dégradée après 60 s sans signal", w["state"] in ("DEGRADED", "DOWN"), w["detail"])
restore()
t0, back = time.time(), False
while time.time() - t0 < 90 and not back:  # heartbeat every 10 s at most; slow machines need more time to start
    time.sleep(5)
    back = health(mgr)[1]["worker_communications"]["state"] == "OK"
check("Worker relancé : signal de vie revenu", back, f"{time.time() - t0:.0f} s")

# ---------------- PostgreSQL ----------------
code = f"RES-{uuid4().hex[:5].upper()}"
subprocess.run([str(L.PG_BIN / "pg_ctl.exe"), "stop", "-D", str(L.PG_DATA), "-m", "fast", "-w"], capture_output=True, timeout=120)
r = mgr.get("platform/team/me")
check("PostgreSQL arrêté : 503 avec message (pas 500)", r.status_code == 503 and "base de données" in r.json()["detail"], r.status_code)
w = mgr.post("platform/schools", json={"name": "Ne doit pas exister", "code": code}, headers={"Idempotency-Key": str(uuid4())})
check("PostgreSQL arrêté : mutation refusée en 503 (pas de faux succès)", w.status_code == 503, w.status_code)
check("PostgreSQL arrêté : sonde de vie du serveur toujours 200", httpx.get(BASE.replace("/api/v1", "") + "/health", timeout=10).status_code == 200)
restore()
t0, ok = time.time(), False
while time.time() - t0 < 60 and not ok:
    try:
        ok = mgr.get("platform/team/me").status_code == 200
    except Exception:  # noqa: BLE001
        pass
    time.sleep(2)
check("PostgreSQL rétabli : l'API récupère seule (pool revalidé)", ok, f"{time.time() - t0:.0f} s")
with owner.connect() as c:
    ghost = c.execute(text("SELECT count(*) FROM schools WHERE code=:c"), {"c": code}).scalar_one()
check("Aucun faux succès : l'école refusée pendant la panne n'existe pas", ghost == 0)
check("Session conservée à travers la panne (pas de reconnexion)", mgr.get("platform/team/me").status_code == 200)

out = Path(__file__).with_name("resilience-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
