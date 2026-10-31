"""Offline replays — real HTTP + real PostgreSQL (2026-10-31, owner: « au niveau école tout le monde peut travailler offline »).

Every school role now works offline: the device keeps each operation with its Idempotency-Key and replays it when the
network returns — possibly TWICE when the first answer was lost on the way. This run replays, with the same key, the
operations that were not replay-safe before: a cash expense (recorded twice → wrong cash), the stewardship updates
(item card, asset card, asset status, repair, count line, count validation). Each must apply exactly ONCE and answer the
first result again; a different key keeps the business rules (409 where the operation is really new and impossible).

    python tools/local/isolated_db.py env edusync_cert_secretariat -- ../.venv/Scripts/python.exe ../tools/ci/offline_replay_postgres_integration.py

Reuses tools/ci/three_roles_postgres_integration.py (CI=true, localhost only). Exits 1 on any FAIL.
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import three_roles_postgres_integration as H  # noqa: E402
from three_roles_postgres_integration import actor_for, as_, check, key, one, school  # noqa: E402


def twice(method: str, path: str, body: dict | None = None, extra: dict | None = None):
    k = {**key(), **(extra or {})}
    c = H.CLIENT
    return c.request(method, path, json=body, headers=k), c.request(method, path, json=body, headers=k)


def cash(A: dict) -> None:
    print("\n== Caisse : dépense rejouée")
    as_(actor_for("CAISSIER", A["id"]))
    o = H.CLIENT.post("/api/v1/finance/cash/open", json={"opening_cdf": "50000", "opening_usd": "0"}, headers=key())
    check("caisse ouverte", o.status_code in (200, 201), o.text[:150])
    reason = f"Craies {H.RUN}"
    r1, r2 = twice("POST", "/api/v1/finance/cash/expenses", {"category": "Fournitures", "amount": "1500", "currency": "CDF", "reason": reason})
    n = one("SELECT count(*) FROM finance_cash_expenses WHERE reason=:r", r=reason)[0]
    check("dépense rejouée avec la même clé : une seule ligne, même réponse", r1.status_code == 201 and r2.status_code == 201 and r1.json().get("id") == r2.json().get("id") and n == 1,
          f"{r1.status_code}/{r2.status_code} lignes={n}")
    r3 = H.CLIENT.post("/api/v1/finance/cash/expenses", json={"category": "Fournitures", "amount": "1500", "currency": "CDF", "reason": reason}, headers=key())
    check("même dépense avec une AUTRE clé : c'est une nouvelle dépense (2 lignes)", r3.status_code == 201 and one("SELECT count(*) FROM finance_cash_expenses WHERE reason=:r", r=reason)[0] == 2)
    k = key()
    a = H.CLIENT.post("/api/v1/finance/cash/expenses", json={"category": "Fournitures", "amount": "1500", "currency": "CDF", "reason": reason}, headers=k)
    b = H.CLIENT.post("/api/v1/finance/cash/expenses", json={"category": "Fournitures", "amount": "9999", "currency": "CDF", "reason": reason}, headers=k)
    check("même clé, autre montant → 409 (jamais une dépense inventée)", a.status_code == 201 and b.status_code == 409, b.status_code)


def stewardship(A: dict) -> None:
    print("\n== Intendance : mises à jour rejouées")
    as_(actor_for("INTENDANT", A["id"]))
    c = H.CLIENT
    item = c.post("/api/v1/stewardship/items", json={"code": f"PAPIER{H.RUN}", "label": "Papier", "unit": "rame", "low_threshold": "2"}, headers=key()).json()["id"]
    c.post("/api/v1/stewardship/stock/movements", json={"item_id": item, "movement_type": "RECEIPT", "quantity": "10", "reason": "Réception"}, headers=key())
    ver = one("SELECT version FROM inventory_items WHERE id=:i", i=item)[0]
    r1, r2 = twice("PUT", f"/api/v1/stewardship/items/{item}", {"label": "Papier A4", "unit": "rame", "low_threshold": "3", "location_id": None, "enabled": True}, {"If-Match": str(ver)})
    check("fiche article rejouée (If-Match) : 200 deux fois, une seule nouvelle version", r1.status_code == 200 and r2.status_code == 200 and r1.json() == r2.json()
          and one("SELECT version FROM inventory_items WHERE id=:i", i=item)[0] == ver + 1, f"{r1.status_code}/{r2.status_code}")
    asset = c.post("/api/v1/stewardship/assets", json={"asset_type_id": str(A["asset_type"]), "quantity": 2}, headers=key()).json()["id"]
    av = one("SELECT version FROM inventory_assets WHERE id=:i", i=asset)[0]
    r1, r2 = twice("PUT", f"/api/v1/stewardship/assets/{asset}", {"tag": "B-01", "notes": "Salle 3", "quantity": 2, "version": av})
    check("fiche d'un bien rejouée : 200 deux fois, une seule modification tracée", r1.status_code == 200 and r2.status_code == 200
          and one("SELECT count(*) FROM inventory_asset_events WHERE asset_id=:i AND event_type='UPDATE'", i=asset)[0] == 1, f"{r1.status_code}/{r2.status_code} {r2.text[:100]}")
    r1, r2 = twice("POST", f"/api/v1/stewardship/assets/{asset}/status", {"status": "TO_REPAIR", "reason": "Pied cassé"})
    check("changement d'état rejoué : un seul événement", r1.status_code == 200 and r2.status_code == 200
          and one("SELECT count(*) FROM inventory_asset_events WHERE asset_id=:i AND to_status='TO_REPAIR'", i=asset)[0] == 1)
    r1, r2 = twice("POST", f"/api/v1/stewardship/assets/{asset}/repairs", {"reason": "Envoyé chez le menuisier", "completed": False})
    check("réparation rejouée : une seule intervention dans l'historique (avant : deux)", r1.status_code == 200 and r2.status_code == 200
          and one("SELECT count(*) FROM inventory_asset_events WHERE asset_id=:i AND event_type='REPAIR'", i=asset)[0] == 1, f"{r1.status_code}/{r2.status_code}")
    cnt = c.post("/api/v1/stewardship/counts", json={"notes": "Rejeu"}, headers=key()).json()["id"]
    r1, r2 = twice("POST", f"/api/v1/stewardship/counts/{cnt}/lines", {"item_id": item, "counted_quantity": "8", "reason": "Deux rames abîmées"})
    check("ligne de comptage rejouée : une seule ligne", r1.status_code == 200 and r2.status_code == 200 and one("SELECT count(*) FROM inventory_count_lines WHERE count_id=:c", c=cnt)[0] == 1)
    r1, r2 = twice("POST", f"/api/v1/stewardship/counts/{cnt}/validate")
    check("validation d'inventaire rejouée : 200 deux fois (avant : 409 « déjà validé »), un seul ajustement, stock = 8",
          r1.status_code == 200 and r2.status_code == 200 and float(one("SELECT quantity FROM inventory_items WHERE id=:i", i=item)[0]) == 8
          and one("SELECT count(*) FROM inventory_item_movements WHERE item_id=:i AND movement_type='COUNT_ADJUSTMENT'", i=item)[0] == 1, f"{r1.status_code}/{r2.status_code}")
    check("nouvelle validation avec une autre clé → 409 (règle inchangée)", c.post(f"/api/v1/stewardship/counts/{cnt}/validate", headers=key()).status_code == 409)
    check("sans clé : comportement historique conservé (état inchangé → 200)", c.post(f"/api/v1/stewardship/assets/{asset}/status", json={"status": "IN_REPAIR", "reason": "En atelier"}).status_code == 200)


def main() -> int:
    A = school("A")
    cash(A)
    stewardship(A)
    H.CLIENT.__exit__(None, None, None)
    fails = [r for r in H.RESULTS if r[0] == "FAIL"]
    print(f"\n{len(H.RESULTS) - len(fails)}/{len(H.RESULTS)} PASS · {len(fails)} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
