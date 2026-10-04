"""D15: behind a reverse proxy, distinct users must not share one throttling identity.

Usage: proxy_ip_probe.py <base_url> <label>
The target uvicorn instance is started with or without proxy trust; nginx is simulated by the
X-Forwarded-For header it sets ($proxy_add_x_forwarded_for)."""
import os
import sys
from uuid import uuid4

import httpx
import redis

sys.path.insert(0, os.path.dirname(__file__))
from common import *  # noqa: E402,F403

base, label = sys.argv[1], sys.argv[2]
rds = redis.Redis.from_url(os.environ["EDUSYNC_REDIS_URL"], socket_timeout=3)
for k in rds.scan_iter("edusync:auth:fail:*"):
    rds.delete(k)
A = state["A"]
legit = A["users"]["CAISSIER1"]
c = httpx.Client(base_url=base, timeout=30)
# attacker at 203.0.113.7 sprays wrong passwords on random accounts
for i in range(8):
    c.post("/api/v1/auth/login", headers={"X-Forwarded-For": "203.0.113.7"},
           json={"email": f"spray{i}-{uuid4().hex[:4]}@example.test", "password": "x" * 12, "scope": "SCHOOL", "school_code": A["code"]})
# a different, legitimate parent-school user at 198.51.100.20 logs in correctly
r = c.post("/api/v1/auth/login", headers={"X-Forwarded-For": "198.51.100.20"},
           json={"email": legit["email"], "password": legit["password"], "scope": "SCHOOL", "school_code": A["code"]})
check(f"[{label}] attacker's failures do not lock out a different user behind the proxy", r.status_code == 200, f"HTTP {r.status_code}")
r = c.post("/api/v1/auth/login", headers={"X-Forwarded-For": "203.0.113.7"},
           json={"email": f"spray-x-{uuid4().hex[:4]}@example.test", "password": "x" * 12, "scope": "SCHOOL", "school_code": A["code"]})
check(f"[{label}] the attacker's own IP is throttled", r.status_code == 429, f"HTTP {r.status_code}")
for k in rds.scan_iter("edusync:auth:fail:*"):
    rds.delete(k)
dump(f"proxy-ip-{label}.json")
