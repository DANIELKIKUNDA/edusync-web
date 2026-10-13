"""Live probe — N1 platform audit: filters, detail before/after, correlation, CSV export (bounded, audited,
formula-injection safe), append-only guarantees, permissions, performance."""
import json
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import BASE, owner, platform, platform_login, state  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


mgr = platform()
# A role created with a formula-looking reason/label feeds the export test.
run = uuid4().hex[:6].upper()
mgr.post("platform/team/roles", json={"code": f"AUDITPROBE_{run}", "label": "=HYPERLINK(\"x\")", "capabilities": []}, headers={"Idempotency-Key": str(uuid4())})

r = mgr.get("platform/audit-log", params={"limit": 20})
d = r.json()
check("Audit : liste paginée (200), curseur suivant", r.status_code == 200 and len(d["items"]) == 20 and d["next_cursor"], r.status_code)
nxt = mgr.get("platform/audit-log", params={"limit": 20, "cursor_at": d["next_cursor"]["at"], "cursor_id": d["next_cursor"]["id"]}).json()
check("Audit : page suivante sans recouvrement", not ({x["id"] for x in d["items"]} & {x["id"] for x in nxt["items"]}))
f = mgr.get("platform/audit-log", params={"action": "PLATFORM_ROLE_CREATED"}).json()["items"]
check("Filtre par action", f and all(x["action"] == "PLATFORM_ROLE_CREATED" for x in f), len(f))
sc = state["A"]["code"]
f = mgr.get("platform/audit-log", params={"school": sc}).json()["items"]
check("Filtre par école (code)", f and all((x["school_code"] or "").upper() == sc.upper() for x in f), len(f))
f = mgr.get("platform/audit-log", params={"scope": "PLATFORM"}).json()["items"]
check("Filtre portée plateforme", f and all(x["school_id"] is None for x in f), len(f))
f = mgr.get("platform/audit-log", params={"actor": "Certification"}).json()["items"]
check("Filtre par auteur", f and all("Certification" in (x["actor"] or "") for x in f), len(f))
today = date.today().isoformat()
f = mgr.get("platform/audit-log", params={"date_from": today, "date_to": today}).json()["items"]
check("Filtre par période (jour inclus)", f and all(x["occurred_at"][:10] >= (date.today() - timedelta(days=1)).isoformat() for x in f), len(f))
f = mgr.get("platform/audit-log", params={"q": "Recette N1"}).json()["items"]
check("Recherche plein texte (action, objet, motif)", f and all("Recette N1" in (x["reason"] or "") or "RECETTE" in x["action"] for x in f), len(f))
check("Filtre invalide refusé proprement (422)", mgr.get("platform/audit-log", params={"scope": "NIMPORTE"}).status_code == 422)

with owner.connect() as c:
    ev = c.execute(text("""SELECT id FROM audit_events WHERE action='PLATFORM_ROLE_UPDATED' OR (old_json IS NOT NULL AND new_json IS NOT NULL)
        ORDER BY occurred_at DESC LIMIT 1""")).scalar_one()
det = mgr.get(f"platform/audit-log/{ev}").json()
check("Détail : avant/après, auteur, portée, corrélation", "old_json" in det and "new_json" in det and "actor" in det and "related" in det, list(det)[:8])
check("Détail : clé d'idempotence interne non exposée", "idempotency_key" not in det)
check("Détail inconnu -> 404", mgr.get(f"platform/audit-log/{uuid4()}").status_code == 404)

# Export
check("Export sans date de début refusé (borne obligatoire)", mgr.get("platform/audit-log/export.csv").status_code == 422)
check("Export > 92 jours refusé", mgr.get("platform/audit-log/export.csv", params={"date_from": "2025-01-01", "date_to": today}).status_code == 422)
ex = mgr.get("platform/audit-log/export.csv", params={"date_from": today})
body = ex.content.decode("utf-8-sig")
check("Export CSV (UTF-8 BOM, ; séparateur, en-tête français)", ex.status_code == 200 and body.startswith("Date (UTC);École;Auteur") and ex.headers["content-type"].startswith("text/csv"), ex.status_code)
check("Export : no-store et pièce jointe", "no-store" in ex.headers.get("cache-control", "") and "attachment" in ex.headers.get("content-disposition", ""))
check("Export : aucune cellule ne commence par = + - @ (injection de formule neutralisée)",
      all(not cell[:1] in ("=", "+", "-", "@") for line in body.splitlines()[1:] for cell in line.split(";")))
with owner.connect() as c:
    n = c.execute(text("SELECT count(*) FROM audit_events WHERE action='PLATFORM_AUDIT_EXPORTED' AND occurred_at>now()-interval '1 minute'")).scalar_one()
check("Export lui-même tracé dans l'audit", n >= 1, n)

# Append-only
for label, stmt in (("UPDATE", "UPDATE audit_events SET reason='falsifié' WHERE id=(SELECT id FROM audit_events LIMIT 1)"),
                    ("DELETE", "DELETE FROM audit_events WHERE id=(SELECT id FROM audit_events LIMIT 1)")):
    for role, url in (("propriétaire", os.environ["EDUSYNC_OWNER_DATABASE_URL"]), ("plateforme", os.environ["EDUSYNC_PLATFORM_DATABASE_URL"])):
        try:
            with create_engine(url, pool_size=1).begin() as c:
                c.execute(text(stmt))
            check(f"Append-only : {label} refusé ({role})", False, "accepté")
        except Exception as e:  # noqa: BLE001
            check(f"Append-only : {label} refusé ({role})", True, type(e).__name__)

# Permissions: an account without platform.audit.read / export.
u2 = state.get("N1_TEAM", {}).get("u2")
if u2:
    lr = platform_login(u2["email"], u2["password"])
    if lr.status_code == 200:
        c = httpx.Client(base_url=BASE + "/", headers={"Authorization": "Bearer " + lr.json()["access_token"]}, timeout=30)
        perms = set(c.get("platform/team/me").json()["permissions"])
        check("Sans platform.audit.read : lecture refusée", c.get("platform/audit-log").status_code == (200 if "platform.audit.read" in perms else 403))
        check("Sans platform.audit.export : export refusé", c.get("platform/audit-log/export.csv", params={"date_from": today}).status_code == (200 if "platform.audit.export" in perms else 403))

t0 = time.perf_counter()
for p in ({}, {"action": "SCHOOL_CREATED"}, {"actor": "Cert"}, {"scope": "PLATFORM"}, {"q": "rôle"}):
    mgr.get("platform/audit-log", params=p)
avg = (time.perf_counter() - t0) / 5 * 1000
with owner.connect() as c:
    total = c.execute(text("SELECT count(*) FROM audit_events")).scalar_one()
check("Performance : recherche d'audit < 300 ms en moyenne", avg < 300, f"{avg:.0f} ms sur {total} événements")

out = Path(__file__).with_name("audit-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
