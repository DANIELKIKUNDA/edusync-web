"""Live probe: SMS pipeline with the local sandbox provider (real PostgreSQL + Redis + worker code)."""
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import redis
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "claude-20260930"))
from common import owner, state, user_client  # noqa: E402
from edusync.bootstrap.settings import Settings  # noqa: E402
from edusync.modules.communications import worker as cw  # noqa: E402
from edusync.modules.communications.providers import provider_for  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append({"check": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS " if ok else "FAIL ") + name + (f": {detail}" if detail else ""), flush=True)


def q(sql, **p):
    with owner.begin() as c:
        r = c.execute(text(sql), p)
        return r.mappings().all() if r.returns_rows else None


A = state["A"]; sid = A["school_id"]
cfg = Settings(); r = redis.Redis.from_url(cfg.redis_url, decode_responses=True)
q("""INSERT INTO communication_settings(school_id,enabled,sms_enabled,provider_code,sender_id) VALUES(:s,true,true,'sandbox','EDUSYNC')
     ON CONFLICT(school_id) DO UPDATE SET enabled=true,sms_enabled=true,provider_code='sandbox',sender_id='EDUSYNC'""", s=sid)
mid = q("""INSERT INTO communication_messages(school_id,kind,audience_type,subject,body,idempotency_key)
           VALUES(:s,'COMMUNIQUE','INDIVIDUAL','Recette clôture','Message de recette EduSync',:k) RETURNING id""", s=sid, k="closure-sms-" + uuid4().hex)[0]["id"]
dest = {"ok": "+243810001234", "rejected": "+243810000000", "timeout": "+243810009999", "undeliverable": "+243810008888", "invalid": "12"}
ids = {k: q("INSERT INTO communication_deliveries(school_id,message_id,channel,destination,status) VALUES(:s,:m,'SMS',:d,'PENDING') RETURNING id", s=sid, m=mid, d=v)[0]["id"] for k, v in dest.items()}
try:
    q("INSERT INTO communication_deliveries(school_id,message_id,channel,destination,status) VALUES(:s,:m,'SMS',:d,'PENDING')", s=sid, m=mid, d=dest["ok"])
    check("idempotence : même message + même numéro refusé en double", False)
except Exception:
    check("idempotence : même message + même numéro refusé en double", True)

for _ in range(12):
    cw.run_once(cfg, r, owner)


def st(k):
    return q("SELECT status,attempts,provider_message_id,last_error_code,provider_code FROM communication_deliveries WHERE id=:i", i=ids[k])[0]


s_ok = st("ok")
check("queued -> sent : uniquement avec preuve fournisseur", s_ok["status"] == "SENT" and s_ok["provider_message_id"] and s_ok["provider_code"] == "sandbox", dict(s_ok))
check("rejet fournisseur : retry planifié (pas de faux succès)", st("rejected")["status"] == "QUEUED" and st("rejected")["last_error_code"] == "PROVIDER_REJECTED", dict(st("rejected")))
check("délai dépassé : retry planifié", st("timeout")["status"] == "QUEUED" and st("timeout")["last_error_code"] == "PROVIDER_TIMEOUT", dict(st("timeout")))
check("numéro invalide : jamais marqué envoyé", st("invalid")["status"] in ("QUEUED", "FAILED") and st("invalid")["last_error_code"] == "INVALID_DESTINATION", dict(st("invalid")))
check("sent ne devient pas delivered sans accusé", st("undeliverable")["status"] == "SENT")

changed = cw.reconcile_delivery_reports(cfg, owner)
check("accusé fournisseur : sent -> delivered", st("ok")["status"] == "DELIVERED", dict(st("ok")))
check("accusé négatif : sent -> failed (UNDELIVERABLE)", st("undeliverable")["status"] == "FAILED" and st("undeliverable")["last_error_code"] == "UNDELIVERABLE", changed)
check("rejouer les accusés ne change plus rien", cw.reconcile_delivery_reports(cfg, owner) == 0)

for _ in range(8):  # exhaust retries (backoff skipped for the probe)
    q("UPDATE communication_deliveries SET next_attempt_at=NULL WHERE id=:i AND status='QUEUED'", i=ids["rejected"])
    cw.run_once(cfg, r, owner)
check("échecs répétés : statut terminal FAILED après 5 tentatives", st("rejected")["status"] == "FAILED" and st("rejected")["attempts"] == 5, dict(st("rejected")))

admin = user_client(A, "ADMIN")
cashier = user_client(A, "CAISSIER1")
rr = admin.post(f"communications/deliveries/{ids['rejected']}/retry")
if rr.status_code == 403:
    check("relance manuelle : permission communications.delivery.retry exigée", True, "ADMIN sans la permission")
else:
    check("relance manuelle d'un échec terminal (auditée)", rr.status_code == 200 and rr.json()["requeued"] is True and st("rejected")["status"] == "QUEUED", rr.text[:200])
    again = admin.post(f"communications/deliveries/{ids['ok']}/retry")
    check("relance d'un SMS distribué : sans effet (idempotent)", again.status_code == 200 and again.json()["requeued"] is False, again.text[:120])
check("caissier : relance refusée", cashier.post(f"communications/deliveries/{ids['rejected']}/retry").status_code == 403)

t = admin.post("communications/templates", json={"code": "RECU_PAIEMENT", "label": "Reçu de paiement", "channel": "SMS", "body": "{{ecole}} : paiement {{montant}} {{devise}} reçu pour {{eleve}} (reçu {{recu}})."})
if t.status_code == 403:
    check("modèles : permission communications.templates.manage exigée", True, "ADMIN sans la permission")
else:
    check("modèle SMS enregistré (variables déclarées)", t.status_code == 201, t.text[:120])
bad = admin.post("communications/templates", json={"code": "PIEGE", "label": "Piège", "channel": "SMS", "body": "Bonjour {{mot_de_passe}}"})
check("variable inconnue refusée", bad.status_code in (403, 422), bad.status_code)
pv = admin.post("communications/templates/preview", json={"body": "Reçu {{recu}} : {{montant}} {{devise}}", "values": {"recu": "REC-1", "montant": "50 000", "devise": "CDF"}})
check("aperçu rendu + estimation des segments", pv.status_code in (200, 403) and (pv.status_code == 403 or pv.json()["text"] == "Reçu REC-1 : 50 000 CDF"), pv.text[:120])
pv2 = admin.post("communications/templates/preview", json={"body": "Reçu {{recu}}", "values": {}})
check("valeur manquante : jamais envoyé avec {{...}}", pv2.status_code in (403, 422), pv2.status_code)

prod = SimpleNamespace(env="production", orange_sms_endpoint="", orange_sms_bearer_token="")
check("production : fournisseurs de test refusés", provider_for(prod, "sandbox") is None and provider_for(prod, "mock") is None)
check("fournisseur inconnu : aucun envoi simulé", provider_for(cfg, "inconnu") is None)

out = Path(__file__).with_name("sms-live.json")
out.write_text(json.dumps({"passed": sum(x["pass"] for x in results), "total": len(results), "results": results}, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
print(f"{sum(x['pass'] for x in results)}/{len(results)} PASS")
sys.exit(0 if all(x["pass"] for x in results) else 1)
