"""Local probe of the platform messaging cockpit (lot 2026-10): provider states, worker health checks, queue explorer,
diagnosable failures, manual retry (capability, reason, step-up, idempotence, never an SMS), SMS wallets (required
recharge fields, separate adjustment capability, no negative balance, balance before/after), RBAC, no secret.
Real local stack (API 58100, worker, PostgreSQL, Redis) with the development simulators: a « bounce… » address makes
the simulated e-mail provider refuse permanently. Everything created is removed or neutral.
Usage: EDUSYNC_LOCAL_PG_PORT=54432 python tools/local/messaging_cockpit_probe.py
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend/src")); sys.path.insert(0, str(ROOT / "tools/local"))
import edusync_local as L  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402
from edusync.shared.infrastructure.mfa import current_step, totp_code  # noqa: E402

API = "http://127.0.0.1:58100/api/v1"
env = L.load_env("demo")
owner = create_engine(env["EDUSYNC_OWNER_DATABASE_URL"])
FX = json.loads((ROOT / ".local/claude-fixtures-edusync_claude_fresh.json").read_text(encoding="utf-8"))
ENV = {l.split("=", 1)[0]: l.rstrip("\n").split("=", 1)[1] for l in (ROOT / ".local/certification.env").read_text(encoding="utf-8").splitlines() if "=" in l and not l.startswith("#")}
FAILS = 0
TAG = uuid.uuid4().hex[:6]


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
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode(); return r.status, (json.loads(raw) if raw else None), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw), raw
        except ValueError:
            return e.code, raw, raw


def login(email, password, secret):
    _, step, _ = call("POST", "/auth/login", body={"email": email, "password": password, "scope": "PLATFORM"})
    for _ in range(3):
        while time.time() % 30 > 25:
            time.sleep(0.5)
        code, sess, _ = call("POST", "/auth/mfa/verify", body={"mfa_token": step["mfa_token"], "code": totp_code(secret, current_step())})
        if code == 200:
            return sess["access_token"]
        time.sleep(31)
    raise SystemExit("connexion impossible")


mgr = login("certification@example.test", ENV["EDUSYNC_PLATFORM_ADMIN_PASSWORD"], FX["MFA_TOTP"]["certification@example.test"]["secret"])
u2 = FX["N1_TEAM"]["u2"]
sup = login(u2["email"], u2["password"], FX["MFA_TOTP"][u2["email"]]["secret"])
MGR_ID = sql("SELECT id FROM users WHERE email='certification@example.test'")[0]["id"]

# ---------------------------------------------------------------- provider states + real checks of the worker
code, st, raw = call("GET", "/platform/messaging/status", mgr)
chans = {c["channel"]: c for c in st["channels"]}
check(code == 200 and set(chans) == {"PUSH", "EMAIL", "SMS"}, "cockpit : un état par canal (push, e-mail, SMS)")
check(all(c["state"] in ("NOT_CONFIGURED", "CONFIGURED", "OPERATIONAL", "DEGRADED", "UNAVAILABLE") for c in chans.values()),
      "états normalisés : " + ", ".join(f"{k} {v['state']}" for k, v in chans.items()))
check(all(c["simulated"] and c["state"] == "NOT_CONFIGURED" for c in chans.values()), "simulation locale jamais « opérationnelle » ni certifiée")
check(all(c["reasons"] for c in chans.values()), "chaque état est expliqué : " + " | ".join(c["reasons"][0] for c in chans.values()))
before = st.get("health_checked_at")
code, b, _ = call("POST", "/platform/messaging/health-check", mgr)
code2, b2, _ = call("POST", "/platform/messaging/health-check", mgr)
check(code == 202 and b["requested"] and code2 == 202 and not b2["requested"], "contrôle réel à la demande, délai de 30 s partagé (pas de rafale)")
for _ in range(20):
    time.sleep(1.5)
    _, st, raw = call("GET", "/platform/messaging/status", mgr)
    if st.get("health_checked_at") and st["health_checked_at"] != before:
        break
check(st.get("health_checked_at") != before and all(c["health"] and c["health"]["fresh"] for c in st["channels"]),
      "le worker a mesuré les fournisseurs (sans envoyer de message)")
low = raw.lower()
# variable NAMES (EDUSYNC_SMTP_PASSWORD…) are expected in the diagnosis; VALUES never are
check(not any(x in low for x in ("password\":\"", "\"private_key\"", "client_secret\":", "begin private", ENV.get("EDUSYNC_SMTP_PASSWORD", "§§").lower() or "§§")),
      "aucun secret dans l’état des fournisseurs (noms de variables seulement)")
check(st["queue"]["worker_state"] in ("OK", "LATE", "DOWN") and "oldest_due" in st["queue"], f"file : worker {st['queue']['worker_state']}, attente, relances, quarantaine")

# ---------------------------------------------------------------- a real failure (simulated provider refuses « bounce… »)
from edusync.modules.communications.application.messaging import Recipient, request_message  # noqa: E402
bounce = f"bounce-{TAG}@example.test"
with owner.begin() as c:
    msg = request_message(c, school_id=None, kind="PLATFORM", channels=["EMAIL"], body="Sonde cockpit", subject="Sonde cockpit",
                          recipients=[Recipient("USER", uuid.uuid4(), "Sonde", email=bounce)], idempotency_key=f"cockpit-probe:{TAG}", created_by=None)
deadline = time.time() + 60
row = None
while time.time() < deadline:
    rows = sql("SELECT id, status, attempts FROM communication_deliveries WHERE message_id=:m", m=msg["id"])
    if rows and rows[0]["status"] in ("FAILED_PERMANENT", "SENT"):
        row = rows[0]; break
    time.sleep(1.5)
check(row and row["status"] == "FAILED_PERMANENT", f"échec définitif produit par le fournisseur (tentatives : {row['attempts'] if row else '?'})")
DID = str(row["id"])

# ---------------------------------------------------------------- queue explorer
code, page, raw = call("GET", "/platform/messaging/deliveries?status=FAILED_PERMANENT&channel=EMAIL&limit=5", mgr)
check(code == 200 and all(i["status"] == "FAILED_PERMANENT" and i["channel"] == "EMAIL" for i in page["items"]), "filtres serveur canal + état")
check(bounce not in raw and "bo•••@example.test" in raw, "destinataire masqué partiellement dans la liste")
code, hit, _ = call("GET", f"/platform/messaging/deliveries?q={DID}", mgr)
code2, hit2, _ = call("GET", f"/platform/messaging/deliveries?q={msg['id']}", mgr)
code3, hit3, _ = call("GET", f"/platform/messaging/deliveries?q={bounce}", mgr)
check([i["id"] for i in hit["items"]] == [DID] and DID in [i["id"] for i in hit2["items"]] and DID in [i["id"] for i in hit3["items"]],
      "recherche par identifiant d’envoi, de message, ou adresse exacte (résultat masqué)")
ids, cur, pages = [], None, 0
while pages < 4:
    _, pg, _ = call("GET", "/platform/messaging/deliveries?limit=10" + (f"&cursor={cur}" if cur else ""), mgr)
    ids += [i["id"] for i in pg["items"]]; cur = pg["next_cursor"]; pages += 1
    if not cur:
        break
check(len(ids) == len(set(ids)) and len(ids) >= 10, f"pagination par curseur : {len(ids)} envois sur {pages} page(s), aucun doublon")
check(call("GET", "/platform/messaging/deliveries?cursor=abc", mgr)[0] == 422 and call("GET", "/platform/messaging/deliveries?status=PIRATE", mgr)[0] == 422,
      "curseur forgé ou état inventé : 422")
_, act, _ = call("GET", "/platform/messaging/deliveries?status=ACTIVE_FAILURES", mgr)
check(DID in [i["id"] for i in act["items"]], "compteur « échecs actifs » cliquable : ouvre les envois concernés")

school_row = sql("SELECT id FROM communication_deliveries WHERE school_id IS NOT NULL ORDER BY created_at DESC LIMIT 1")
if school_row:
    sid_ = str(school_row[0]["id"])
    _, sh, _ = call("GET", f"/platform/messaging/deliveries?q={sid_}", mgr)
    code, sd, sraw = call("GET", f"/platform/messaging/deliveries/{sid_}", mgr)
    check(sh["items"] and sh["items"][0]["event"] == "SCHOOL_MESSAGE" and code == 200 and sd["message"]["private"] and '"body"' not in sraw,
          "envoi d’école visible (métadonnées) ; message de l’école privé, jamais lu par la plateforme")
    _, sch, _ = call("GET", "/platform/messaging/deliveries?event=SCHOOL_MESSAGE&limit=5", mgr)
    check(sch["items"] and all(i["school_id"] for i in sch["items"]), "filtre « messages d’école »")
_, af, _ = call("GET", "/platform/messaging/status", mgr)
_, afl, _ = call("GET", "/platform/messaging/deliveries?status=ACTIVE_FAILURES&limit=100", mgr)
check(len(afl["items"]) > 0 or (af["queue"]["dead_7d"] + af["queue"]["retrying"]) == 0, "la carte « Échecs » et la liste ouverte concordent")

# ---------------------------------------------------------------- failure detail
code, d, raw = call("GET", f"/platform/messaging/deliveries/{DID}", mgr)
check(code == 200 and d["error_code"] == "SMTP_550" and d["first_attempt_at"] and d["last_attempt_at"] and d["message_id"] == msg["id"] and d["outbox_id"],
      f"diagnostic : code {d.get('error_code')}, première / dernière tentative, message, outbox")
check(bounce not in raw and d["destination"].startswith("bo•••") and not d["delivered_proof"], "détail sans adresse complète ; « distribué » jamais sans preuve")
check(d["can_retry"] is True, "relance proposée au Manager (capacité dédiée)")

# ---------------------------------------------------------------- manual retry
check(call("POST", f"/platform/messaging/deliveries/{DID}/retry", sup, {"reason": "essai support"}, key=f"k-{TAG}-0")[0] == 403,
      "support sans la capacité de relance : 403")
check(call("POST", f"/platform/messaging/deliveries/{DID}/retry", mgr, {"reason": "x"}, key=f"k-{TAG}-1")[0] == 422, "motif obligatoire (5 caractères)")
check(call("POST", f"/platform/messaging/deliveries/{DID}/retry", mgr, {"reason": "Relance après correction"})[0] == 400, "clé d’idempotence obligatoire")
sql("UPDATE user_device_sessions SET mfa_stepup_at=now()-interval '2 hours' WHERE user_id=:u", u=MGR_ID)
code, b, _ = call("POST", f"/platform/messaging/deliveries/{DID}/retry", mgr, {"reason": "Relance après correction"}, key=f"k-{TAG}-2")
check(code == 403 and isinstance(b.get("detail"), dict) and b["detail"].get("code") == "MFA_STEP_UP_REQUIRED", "relance : confirmation par code exigée")
sql("UPDATE user_device_sessions SET mfa_stepup_at=now() WHERE user_id=:u AND revoked_at IS NULL", u=MGR_ID)
code, b, _ = call("POST", f"/platform/messaging/deliveries/{DID}/retry", mgr, {"reason": "Relance après correction"}, key=f"k-{TAG}-3")
code2, b2, _ = call("POST", f"/platform/messaging/deliveries/{DID}/retry", mgr, {"reason": "Relance après correction"}, key=f"k-{TAG}-3")
check(code == 200 and b["requeued"] and code2 == 200 and b2.get("replayed"), "relance remise en file ; rejeu de la même demande sans effet")
aud = sql("SELECT reason FROM audit_events WHERE action='PLATFORM_MESSAGING_DELIVERY_RETRIED' AND entity_id=CAST(:d AS uuid)", d=DID)
check(len(aud) == 1 and aud[0]["reason"] == "Relance après correction", "relance journalisée une fois, avec son motif")
time.sleep(6)
final = sql("SELECT status, attempts FROM communication_deliveries WHERE id=:d", d=DID)[0]
check(final["status"] == "FAILED_PERMANENT" and final["attempts"] == 1, "après relance : une seule nouvelle tentative (pas de double envoi)")
sms = sql("SELECT id FROM communication_deliveries WHERE channel='SMS' AND status='FAILED_PERMANENT' LIMIT 1")
if sms:
    check(call("POST", f"/platform/messaging/deliveries/{sms[0]['id']}/retry", mgr, {"reason": "Essai SMS plateforme"}, key=f"k-{TAG}-4")[0] == 409,
          "un SMS ne se relance pas depuis la plateforme (portefeuille de l’école)")
sent = sql("SELECT id FROM communication_deliveries WHERE status='SENT' AND channel='EMAIL' LIMIT 1")
if sent:
    code, b, _ = call("POST", f"/platform/messaging/deliveries/{sent[0]['id']}/retry", mgr, {"reason": "Relance inutile"}, key=f"k-{TAG}-5")
    check(code == 200 and not b["requeued"], "envoi déjà réussi : aucune relance (aucun doublon)")

# ---------------------------------------------------------------- SMS wallets
code, w, _ = call("GET", "/platform/messaging/wallets?limit=10", mgr)
code2, w2, _ = call("GET", f"/platform/messaging/wallets?limit=10&cursor={w['next_cursor']}", mgr)
check(code == 200 and len(w["items"]) == 10 and w["next_cursor"] and not ({i["school_id"] for i in w["items"]} & {i["school_id"] for i in w2["items"]}),
      "portefeuilles : pagination serveur sans doublon")
check({"balance", "reserved", "available"} <= set(w["totals"]) and all({"balance", "reserved", "available"} <= set(i) for i in w["items"]),
      "solde total, réservé et disponible distincts")
A = FX["A"]["school_id"]
code, s, _ = call("GET", f"/platform/messaging/wallets?q={FX['A']['code'][:6]}", mgr)
check(any(i["school_id"] == A for i in s["items"]), "recherche d’école par nom ou code")
base = {"quantity": 50, "reference": f"FACT-{TAG}", "reason": "Achat de crédits SMS"}
check(call("POST", f"/platform/messaging/wallets/{A}/credit", mgr, base, key=f"t-{TAG}-0")[0] == 422, "recharge sans date, montant et devise : 422")
check(call("POST", f"/platform/messaging/wallets/{A}/credit", mgr, {**base, "paid_on": "2099-01-01", "commercial_price": 10, "commercial_currency": "USD"},
           key=f"t-{TAG}-1")[0] == 422, "date de paiement future : 422")
check(call("POST", f"/platform/messaging/wallets/{A}/credit", mgr, {**base, "quantity": -5, "paid_on": "2026-10-19", "commercial_price": 10,
                                                                    "commercial_currency": "USD"}, key=f"t-{TAG}-2")[0] == 422, "quantité négative : 422")
full = {**base, "paid_on": "2026-10-19", "commercial_price": 12.5, "commercial_currency": "USD"}
code, t1, _ = call("POST", f"/platform/messaging/wallets/{A}/credit", mgr, full, key=f"t-{TAG}-3")
code2, t2, _ = call("POST", f"/platform/messaging/wallets/{A}/credit", mgr, full, key=f"t-{TAG}-3")
check(code == 200 and t1["balance"] == t1["balance_before"] + 50 and t2["replayed"] and t2["balance"] == t1["balance"],
      f"recharge : solde {t1.get('balance_before')} → {t1.get('balance')} ; rejeu sans double crédit")
check(call("POST", f"/platform/messaging/wallets/{A}/credit", sup, full, key=f"t-{TAG}-4")[0] == 403, "support : recharge refusée (403)")
check(call("POST", f"/platform/messaging/wallets/{A}/adjust", mgr, {"direction": "DEBIT", "quantity": 1, "reason": "court"}, key=f"a-{TAG}-0")[0] == 422,
      "ajustement : justification de 10 caractères au moins")
code, neg, _ = call("POST", f"/platform/messaging/wallets/{A}/adjust", mgr, {"direction": "DEBIT", "quantity": 10_000_000, "reason": "Débit impossible de test"},
                    key=f"a-{TAG}-1")
check(code == 409, "débit au-delà du disponible refusé : jamais de solde négatif")
code, adj, _ = call("POST", f"/platform/messaging/wallets/{A}/adjust", mgr, {"direction": "DEBIT", "quantity": 50, "reason": "Annulation de la recharge de sonde"},
                    key=f"a-{TAG}-2")
check(code == 200 and adj["balance"] == t1["balance"] - 50, "ajustement débiteur motivé (remet le solde de départ)")
code, led, _ = call("GET", f"/platform/messaging/wallets/{A}/ledger?limit=5", mgr)
top = next(x for x in led["items"] if x["reference"] == f"FACT-{TAG}")
check(top["balance_before"] == t1["balance_before"] and top["balance_after"] == t1["balance"] and top["commercial_currency"] == "USD",
      "grand livre : solde avant / après, montant et devise de la recharge")
audits = sql("SELECT action, new_json FROM audit_events WHERE action IN ('SMS_WALLET_TOPUP','SMS_WALLET_ADJUSTMENT') AND idempotency_key LIKE :k", k=f"%-{TAG}-%")
check(len(audits) == 2 and any(a["new_json"].get("paid_on") == "2026-10-19" for a in audits), "recharge et ajustement journalisés (date de paiement incluse)")

# ---------------------------------------------------------------- test send + RBAC
check(call("POST", "/platform/messaging/test-send", mgr, {"channel": "PUSH"})[0] in (200, 409), "test push : refusé proprement sans appareil enregistré (409) ou mis en file")
check(call("GET", "/platform/messaging/status")[0] == 401 and call("GET", "/platform/messaging/deliveries")[0] == 401, "sans jeton : 401")
school = FX["A"]["users"]["CAISSIER1"]
_, ss, _ = call("POST", "/auth/login", body={"email": school["email"], "password": school["password"], "scope": "SCHOOL", "school_code": FX["A"]["code"]})
if isinstance(ss, dict) and ss.get("access_token"):
    check(call("GET", "/platform/messaging/deliveries", ss["access_token"])[0] in (401, 403), "jeton école refusé sur la messagerie plateforme")

sql("DELETE FROM communication_deliveries WHERE message_id=:m", m=msg["id"])
print("\nRÉSULTAT : " + ("PASS" if FAILS == 0 else f"FAIL ({FAILS})"))
sys.exit(1 if FAILS else 0)
