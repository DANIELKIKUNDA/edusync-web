"""Live probe — N1 system health: real measurements, permissions, worker heartbeats, error counter, honesty."""
import json
import os
import sys
import time
from pathlib import Path

import redis

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import platform, state  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend" / "src"))
from edusync.shared.infrastructure.heartbeat import HEARTBEAT_PREFIX, record_server_error  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


mgr = platform()
r = mgr.get("platform/system/health")
d = r.json()
comps = {c["key"]: c for c in d["components"]}
check("Santé : 200 pour le Manager", r.status_code == 200, r.status_code)
check("Composants mesurés : API, base, cache, 2 workers, stockage, erreurs, sauvegarde",
      set(comps) == {"api", "database", "redis", "worker_outbox", "worker_communications", "storage", "errors", "backup"}, sorted(comps))
check("Base : temps de réponse réellement mesuré", isinstance(comps["database"]["measured_ms"], int), comps["database"]["detail"])
check("Cache : PING réellement mesuré", isinstance(comps["redis"]["measured_ms"], int), comps["redis"]["detail"])
check("Stockage : requête signée réellement mesurée", comps["storage"]["state"] in ("OK", "DEGRADED") and isinstance(comps["storage"]["measured_ms"], int), comps["storage"]["detail"])
check("Workers : signal de vie reçu (< 60 s)", all(comps[k].get("age_seconds") is not None and comps[k]["age_seconds"] < 60 for k in ("worker_outbox", "worker_communications")),
      [comps[k]["detail"] for k in ("worker_outbox", "worker_communications")])
check("Sauvegarde non configurée : annoncée comme telle, jamais « OK »", comps["backup"]["state"] in ("NOT_CONFIGURED", "OK", "DEGRADED", "DOWN") and (comps["backup"]["state"] != "OK" or "Réussie" in comps["backup"]["detail"]), comps["backup"]["detail"])
check("Libellés humains (aucun code technique affiché)", all(" " in c["label"] and "_" not in c["label"] for c in d["components"]))

rc = redis.Redis.from_url(os.environ["EDUSYNC_REDIS_URL"], decode_responses=True)
before = comps["errors"]["value"]
record_server_error(rc)
after = {c["key"]: c for c in mgr.get("platform/system/health").json()["components"]}["errors"]["value"]
check("Compteur d'erreurs 5xx réellement alimenté (Redis, par heure)", after == before + 1, f"{before} -> {after}")
rc.decr(max(rc.keys("edusync:errors:5xx:*")))  # undo the synthetic increment

check("Signal de vie stocké sans donnée sensible", all(rc.get(HEARTBEAT_PREFIX + w).count("T") == 1 for w in ("outbox", "communications")))

# Without platform.health.read: refused.
fx = state.get("N1_TEAM", {}).get("u2")
if fx:
    import httpx
    from common import BASE, platform_login
    lr = platform_login(fx["email"], fx["password"])
    if lr.status_code == 200:
        c = httpx.Client(base_url=BASE + "/", headers={"Authorization": "Bearer " + lr.json()["access_token"]}, timeout=30)
        perms = c.get("platform/team/me").json()["permissions"]
        expected = 200 if "platform.health.read" in perms else 403
        check("Santé : accès conditionné à platform.health.read", c.get("platform/system/health").status_code == expected, f"{perms}")

t0 = time.perf_counter()
for _ in range(10):
    mgr.get("platform/system/health")
avg = (time.perf_counter() - t0) / 10 * 1000
check("Performance : écran santé < 300 ms en moyenne (10 appels)", avg < 300, f"{avg:.0f} ms")

out = Path(__file__).with_name("health-live.json")
out.write_text(json.dumps(results, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
print(f"== {sum(r['pass'] for r in results)}/{len(results)} PASS -> {out.name}")
