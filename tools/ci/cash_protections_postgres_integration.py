"""Protections of the cash desk — real HTTP + real PostgreSQL (owner, 2026-11-27).

A cashier closed her session at 13 h 26, a second one opened at once, stayed open all night, and this morning's
payments went into it, dated yesterday. Now:
1. no money goes into the session of a past day — close it, then open today's; an operation made offline on that day and
   replayed later (outbox, with its device moment) is still accepted there; a device without the moment is not refused;
2. reopening the same day after a closure is asked first (« Ouvrir une 2e caisse ? »);
3. an opening made offline BEFORE a later closure of the same day is ignored when replayed.

    python tools/local/isolated_db.py env <db> -- ../.venv/Scripts/python.exe ../tools/ci/cash_protections_postgres_integration.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from enrollment_month_postgres_integration import fixture  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, key, one, school, sql  # noqa: E402


def run(A: dict) -> None:
    print("\n== Protections de la caisse (27/11/2026)")
    f = fixture(A)
    as_(actor_for("CAISSIER", A["id"]))
    c = H.CLIENT
    o = c.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key())
    check("caisse ouverte", o.status_code in (200, 201), o.text[:150])
    sid = o.json().get("id")
    sql("UPDATE finance_cash_sessions SET business_date=CURRENT_DATE-1, opened_at=now()-interval '20 hours' WHERE id=:i", i=sid)   # forgotten since yesterday
    pay = lambda ids, amount, extra=None: c.post("/api/v1/finance/checkout/collect", json={"enrollment_id": str(f["enrollment"]), "charge_ids": ids,
                                                                                          "amount": str(amount), "currency": "CDF"}, headers={**key(), **(extra or {})})
    r = pay([f["ins"], f["jun"]], 35000)
    check("1. encaisser dans la caisse d'hier restée ouverte → refusé, avec la marche à suivre",
          r.status_code == 409 and "encore ouverte" in r.text and "clôturez-la" in r.text, f"{r.status_code} {r.text[:160]}")
    e = c.post("/api/v1/finance/cash/expenses", json={"category": "DIVERS", "amount": "1000", "currency": "CDF", "reason": "Craies"}, headers=key())
    check("1. une dépense non plus", e.status_code == 409 and "encore ouverte" in e.text, f"{e.status_code} {e.text[:160]}")
    yesterday_evening = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=15, minute=0).isoformat()
    r = pay([f["ins"], f["jun"]], 35000, {"X-EduSync-Replay": "outbox", "X-EduSync-Made-At": yesterday_evening})
    check("1. un encaissement fait hier hors connexion, envoyé ce matin → accepté dans la caisse d'hier",
          r.status_code in (200, 201) and one("SELECT cash_session_id FROM finance_payments WHERE enrollment_id=:e ORDER BY created_at DESC LIMIT 1",
                                              e=f["enrollment"])[0] is not None, f"{r.status_code} {r.text[:160]}")
    now_ = datetime.now(timezone.utc).isoformat()
    r = pay([f["sep"]], 20000, {"X-EduSync-Replay": "outbox", "X-EduSync-Made-At": now_})
    check("1. un encaissement hors connexion fait aujourd'hui → refusé dans la caisse d'hier", r.status_code == 409, f"{r.status_code} {r.text[:160]}")
    r = pay([f["sep"]], 20000, {"X-EduSync-Replay": "outbox"})
    check("1. un appareil ancien (sans l'heure de l'opération) n'est jamais refusé pour ça", r.status_code in (200, 201), f"{r.status_code} {r.text[:160]}")
    r = c.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key())
    check("ouvrir alors que la caisse d'hier est ouverte → la dit et dit quoi faire", r.status_code == 409 and "Clôturez-la" in r.text, r.text[:160])
    cl = c.post("/api/v1/finance/cash/close", json={"counted_cdf": "55000", "counted_usd": "0"}, headers=key())
    check("clôture de la caisse d'hier", cl.status_code == 200, cl.text[:150])
    o = c.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key())
    check("caisse d'aujourd'hui ouverte", o.status_code in (200, 201), o.text[:150])
    r = pay([f["oct"]], 20000)
    check("encaissement normal dans la caisse du jour", r.status_code in (200, 201), f"{r.status_code} {r.text[:160]}")
    closed_before = datetime.now(timezone.utc).isoformat()
    cl = c.post("/api/v1/finance/cash/close", json={"counted_cdf": "20000", "counted_usd": "0"}, headers=key())
    check("clôture à la mi-journée", cl.status_code == 200, cl.text[:150])
    r = c.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"}, headers=key())
    check("2. rouvrir le même jour → la question est posée d'abord (heure de la clôture)",
          r.status_code == 409 and r.json()["detail"]["code"] == "REOPEN_SAME_DAY" and " h " in r.json()["detail"]["message"], r.text[:200])
    before_close = (datetime.fromisoformat(closed_before) - timedelta(minutes=5)).isoformat()
    r = c.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0"},
               headers={**key(), "X-EduSync-Replay": "outbox", "X-EduSync-Made-At": before_close})
    check("3. une ouverture hors connexion faite AVANT la clôture, renvoyée après → ignorée (aucune caisse rouverte)",
          r.status_code == 409 and "ignorée" in r.text and one("""SELECT count(*) FROM finance_cash_sessions WHERE school_id=:s AND status='OPEN'""",
                                                                s=A["id"])[0] == 0, r.text[:160])
    r = c.post("/api/v1/finance/cash/open", json={"opening_cdf": "0", "opening_usd": "0", "confirm_reopen": True}, headers=key())
    check("2. « Oui, ouvrir une 2e caisse » → ouverte", r.status_code in (200, 201), r.text[:150])


def main() -> int:
    A = school("A")
    run(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
