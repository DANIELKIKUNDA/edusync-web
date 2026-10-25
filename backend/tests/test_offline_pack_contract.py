"""Owner decision 2026-10-25: the school works without internet, then synchronises. The offline pack gives the cash desk
what it needs without network (pupils of the active year + payable charges with the SAME eligibility as balance());
payments recorded offline are replayed with their Idempotency-Key and re-checked by the server."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ROUTER = (ROOT / "backend/src/edusync/modules/finance_checkout/api/router.py").read_text(encoding="utf-8")
REPO = (ROOT / "backend/src/edusync/adapters/postgres_finance_checkout.py").read_text(encoding="utf-8")
OUTBOX = (ROOT / "frontend/src/offline/outbox.ts").read_text(encoding="utf-8")
CONN = (ROOT / "frontend/src/platform/connectivity.ts").read_text(encoding="utf-8")


def test_offline_pack_is_permissioned_and_read_only():
    body = ROUTER.split("@router.get('/offline-pack')", 1)[1].split("@router.", 1)[0]
    assert "need(actor,'finance.checkout.offline_cash')" in body and "need(actor,'finance.checkout.balance.read')" in body
    assert "INSERT" not in body.upper() and "UPDATE" not in body.upper()


def test_pack_reuses_the_cash_desk_eligibility():
    pack = REPO.split("def offline_pack(", 1)[1].split("\n def ", 1)[0]
    assert "self.charges(school_id,p['enrollment_id'])" in pack and "y.status='ACTIVE'" in pack


def test_outbox_replays_with_the_same_idempotency_key_and_keeps_refusals():
    assert "'Idempotency-Key': r.idempotencyKey" in OUTBOX and "status: 'CONFLICT'" in OUTBOX
    assert "s.add(req)" in OUTBOX                                     # never overwrite an operation
    assert "Authorization" not in OUTBOX.split("const req: OutboxRequest", 1)[1].split(";", 1)[0]
    for path in ("enrollments\\/family", "checkout\\/collect$", "checkout\\/family-collect", "cash\\/expenses"):
        assert path in OUTBOX
    assert "queueable=school && !read && !replay" in CONN             # the platform stays read-only offline
