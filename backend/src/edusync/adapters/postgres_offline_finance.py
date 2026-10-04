from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from edusync.modules.finance_offline.domain.models import (
    OfflineFinanceConflict, OfflineFinanceLease, OfflinePaymentCommand, ReceiptToken, money
)


@dataclass(slots=True)
class PostgresOfflineFinanceRepository:
    """PostgreSQL persistence for Finance offline V1 + canonical V2 multi-cashier.

    All methods run inside a caller-owned tenant transaction. V2 allows several active leases
    in one school, but authority over a given charge is exclusive. Wall-clock expiry never
    releases server authority automatically; reconciliation or an explicit incident process does.
    """
    connection: Connection

    @staticmethod
    def _lease(row) -> OfflineFinanceLease:
        m = row._mapping
        return OfflineFinanceLease(
            id=UUID(str(m["id"])), school_id=UUID(str(m["school_id"])),
            cashier_user_id=UUID(str(m["cashier_user_id"])), device_id=UUID(str(m["device_id"])),
            cash_session_id=UUID(str(m["cash_session_id"])), status=m["status"],
            local_stop_at=m["local_stop_at"], max_payments=int(m["max_payments"]),
            max_cdf=Decimal(str(m["max_cdf"])), max_usd=Decimal(str(m["max_usd"])),
        )

    @staticmethod
    def _token(row) -> ReceiptToken:
        m = row._mapping
        return ReceiptToken(
            id=UUID(str(m["id"])), lease_id=UUID(str(m["lease_id"])),
            school_id=UUID(str(m["school_id"])), receipt_no=m["receipt_no"], status=m["status"]
        )

    def blocking_lease(self, school_id: UUID) -> OfflineFinanceLease | None:
        row = self.connection.execute(text("""
            SELECT * FROM offline_finance_leases
             WHERE school_id=:sid AND status IN ('PREPARING','ACTIVE','DRAINING')
             ORDER BY created_at DESC LIMIT 1 FOR UPDATE
        """), {"sid": str(school_id)}).first()
        return None if row is None else self._lease(row)

    def acquire_exclusive_lease(self, *, school_id: UUID, cashier_user_id: UUID, device_id: UUID,
                                cash_session_id: UUID, max_payments: int, max_cdf: str, max_usd: str,
                                receipt_count: int, local_minutes: int):
        if receipt_count < 1 or receipt_count > max_payments:
            raise ValueError("receipt_count doit être compris entre 1 et max_payments")
        if local_minutes < 5 or local_minutes > 720:
            raise ValueError("Fenêtre locale offline autorisée: 5..720 minutes")
        self.connection.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                                {"key": f"offline-finance:{school_id}"})
        if self.blocking_lease(school_id) is not None:
            raise OfflineFinanceConflict("Une caisse offline exclusive est déjà active pour cette école")
        row = self.connection.execute(text("""
            INSERT INTO offline_finance_leases(
              school_id,cashier_user_id,device_id,cash_session_id,status,local_stop_at,
              max_payments,max_cdf,max_usd
            ) VALUES(:sid,:uid,:did,:cs,'PREPARING',now()+make_interval(mins=>:mins),:maxp,:cdf,:usd)
            RETURNING *
        """), {"sid": str(school_id), "uid": str(cashier_user_id), "did": str(device_id),
                 "cs": str(cash_session_id), "mins": local_minutes, "maxp": max_payments,
                 "cdf": str(money(max_cdf)), "usd": str(money(max_usd))}).first()
        if row is None:
            raise RuntimeError("Impossible de créer le lease offline")
        lease = self._lease(row)
        tokens: list[ReceiptToken] = []
        for _ in range(receipt_count):
            token = self.connection.execute(text("""
                INSERT INTO offline_receipt_tokens(school_id,lease_id,receipt_no)
                VALUES(:sid,:lid, next_offline_receipt_no(:sid)) RETURNING *
            """), {"sid": str(school_id), "lid": str(lease.id)}).first()
            if token is None:
                raise RuntimeError("Impossible de préallouer un reçu offline")
            tokens.append(self._token(token))
        return lease, tokens


    def store_charge_snapshots(self, lease_id: UUID, snapshots) -> None:
        lease_row = self.connection.execute(text("""
            SELECT school_id,status FROM offline_finance_leases WHERE id=:id FOR UPDATE
        """), {"id": str(lease_id)}).first()
        if lease_row is None or lease_row._mapping["status"] != "PREPARING":
            raise OfflineFinanceConflict("Le snapshot ne peut être chargé que pendant PREPARING")
        school_id = lease_row._mapping["school_id"]
        rows = list(snapshots)
        if not rows:
            raise OfflineFinanceConflict("Au moins une charge exigible doit être figée pour activer le mode offline")
        for snap in rows:
            self.connection.execute(text("""
                INSERT INTO offline_charge_snapshots(
                  school_id,lease_id,charge_id,enrollment_id,student_id,currency,remaining_amount,charge_version
                ) VALUES(:sid,:lid,:cid,:eid,:stid,:currency,:remaining,:version)
                ON CONFLICT (lease_id,charge_id) DO UPDATE SET
                  enrollment_id=EXCLUDED.enrollment_id,student_id=EXCLUDED.student_id,currency=EXCLUDED.currency,
                  remaining_amount=EXCLUDED.remaining_amount,charge_version=EXCLUDED.charge_version,snapshotted_at=now()
            """), {"sid": str(school_id), "lid": str(lease_id), "cid": str(snap.charge_id),
                     "eid": str(snap.enrollment_id), "stid": str(snap.student_id),
                     "currency": snap.currency, "remaining": str(money(snap.remaining_amount)),
                     "version": snap.version})

    def snapshots_for_lease(self, lease_id: UUID):
        from edusync.modules.finance_offline.domain.models import ChargeSnapshot
        rows = self.connection.execute(text("""
            SELECT charge_id,enrollment_id,student_id,currency,remaining_amount,charge_version
              FROM offline_charge_snapshots WHERE lease_id=:id ORDER BY charge_id
        """), {"id": str(lease_id)}).all()
        return [ChargeSnapshot(
            charge_id=UUID(str(r._mapping["charge_id"])), enrollment_id=UUID(str(r._mapping["enrollment_id"])),
            student_id=UUID(str(r._mapping["student_id"])), currency=r._mapping["currency"],
            remaining_amount=Decimal(str(r._mapping["remaining_amount"])), version=int(r._mapping["charge_version"])
        ) for r in rows]

    def activate_lease(self, lease_id: UUID) -> OfflineFinanceLease:
        row = self.connection.execute(text("""
            UPDATE offline_finance_leases l SET status='ACTIVE',activated_at=now()
             WHERE l.id=:id AND l.status='PREPARING'
               AND EXISTS (SELECT 1 FROM offline_charge_snapshots s WHERE s.lease_id=l.id)
               AND EXISTS (SELECT 1 FROM offline_receipt_tokens t WHERE t.lease_id=l.id AND t.status='AVAILABLE')
             RETURNING l.*
        """), {"id": str(lease_id)}).first()
        if row is None:
            raise OfflineFinanceConflict("Lease non activable: snapshot ou reçus préalloués manquants")
        return self._lease(row)

    def receipt_token(self, token_id: UUID) -> ReceiptToken | None:
        row = self.connection.execute(text(
            "SELECT * FROM offline_receipt_tokens WHERE id=:id FOR UPDATE"
        ), {"id": str(token_id)}).first()
        return None if row is None else self._token(row)

    def consume_receipt_token(self, *, token_id: UUID, lease_id: UUID, operation_id: UUID) -> None:
        row = self.connection.execute(text("""
            UPDATE offline_receipt_tokens
               SET status='CONSUMED', consumed_by_operation_id=:op, consumed_at=now()
             WHERE id=:id AND lease_id=:lid AND status='AVAILABLE'
             RETURNING id
        """), {"op": str(operation_id), "id": str(token_id), "lid": str(lease_id)}).first()
        if row is None:
            raise OfflineFinanceConflict("Reçu offline déjà consommé ou invalide")

    def store_received_command(self, command: OfflinePaymentCommand) -> bool:
        row = self.connection.execute(text("""
            INSERT INTO offline_payment_inbox(
              school_id,lease_id,operation_id,idempotency_key,device_id,cashier_user_id,cash_session_id,
              receipt_token_id,receipt_no,student_id,enrollment_id,currency,amount,mode,journal_seq,payload,
              previous_entry_hash,entry_hash,client_time,status
            ) VALUES(
              :sid,:lid,:op,:idem,:did,:uid,:cs,:token,:receipt,:student,:enrollment,:currency,:amount,:mode,:seq,
              CAST(:payload AS jsonb),:prev,:hash,:client_time,'RECEIVED'
            ) ON CONFLICT DO NOTHING RETURNING operation_id
        """), command_to_params(command)).first()
        if row is not None:
            return True
        existing = self.connection.execute(text("""
            SELECT operation_id,idempotency_key,entry_hash,receipt_no,amount,currency,journal_seq
              FROM offline_payment_inbox
             WHERE school_id=:sid AND (
               operation_id=:op OR idempotency_key=:idem OR receipt_no=:receipt
               OR entry_hash=:hash OR (lease_id=:lid AND journal_seq=:seq)
             )
             FOR UPDATE
        """), {"sid": str(command.school_id), "op": str(command.operation_id),
                 "idem": command.idempotency_key, "receipt": command.receipt_no,
                 "hash": command.entry_hash, "lid": str(command.lease_id), "seq": command.journal_seq}).first()
        if existing is None:
            raise OfflineFinanceConflict("Conflit d'unicité du journal offline")
        m = existing._mapping
        exact_replay = (
            str(m["operation_id"]) == str(command.operation_id)
            and m["idempotency_key"] == command.idempotency_key
            and m["entry_hash"] == command.entry_hash
            and m["receipt_no"] == command.receipt_no
            and Decimal(str(m["amount"])) == money(command.amount)
            and m["currency"] == command.currency
            and int(m["journal_seq"]) == command.journal_seq
        )
        if not exact_replay:
            raise OfflineFinanceConflict("Replay offline incohérent ou reçu/séquence déjà utilisé")
        return False

    def mark_command_applied(self, operation_id: UUID, *, payment_id: UUID | None = None,
                             posting_outcome: str = "APPLIED", residual_credit_amount: Decimal | str = "0.00") -> None:
        self.connection.execute(text("""
            UPDATE offline_payment_inbox
               SET status='APPLIED',payment_id=:pid,processed_at=now(),posting_outcome=:outcome,
                   residual_credit_amount=:residual
             WHERE operation_id=:op AND status IN ('RECEIVED','APPLIED')
        """), {"op": str(operation_id), "pid": None if payment_id is None else str(payment_id),
                  "outcome": posting_outcome, "residual": str(money(residual_credit_amount))})

    def mark_lease_draining(self, lease_id: UUID) -> None:
        self.connection.execute(text("""
            UPDATE offline_finance_leases SET status='DRAINING',draining_at=COALESCE(draining_at,now())
             WHERE id=:id AND status='ACTIVE'
        """), {"id": str(lease_id)})

    def close_lease_if_reconciled(self, lease_id: UUID, *, expected_count: int, expected_cdf: str,
                                  expected_usd: str, final_entry_hash: str | None) -> None:
        lease = self.connection.execute(text("""
            SELECT school_id,status FROM offline_finance_leases WHERE id=:id FOR UPDATE
        """), {"id": str(lease_id)}).first()
        if lease is None or lease._mapping["status"] not in {"ACTIVE","DRAINING"}:
            raise OfflineFinanceConflict("Lease offline introuvable ou non clôturable")
        stats = self.connection.execute(text("""
            SELECT count(*) total_count,
                   count(*) FILTER (WHERE status='APPLIED') applied_count,
                   COALESCE(sum(amount) FILTER (WHERE status='APPLIED' AND currency='CDF'),0) cdf,
                   COALESCE(sum(amount) FILTER (WHERE status='APPLIED' AND currency='USD'),0) usd,
                   (SELECT entry_hash FROM offline_payment_inbox z WHERE z.lease_id=:id AND z.status='APPLIED'
                      ORDER BY z.journal_seq DESC LIMIT 1) final_hash
              FROM offline_payment_inbox WHERE lease_id=:id
        """), {"id": str(lease_id)}).first()._mapping
        consumed = int(self.connection.execute(text("""
            SELECT count(*) FROM offline_receipt_tokens WHERE lease_id=:id AND status='CONSUMED'
        """), {"id": str(lease_id)}).scalar_one())
        if (int(stats["total_count"]) != expected_count or int(stats["applied_count"]) != expected_count
                or consumed != expected_count):
            raise OfflineFinanceConflict("Réconciliation impossible: opération non appliquée ou nombre de reçus différent")
        if Decimal(str(stats["cdf"])) != money(expected_cdf) or Decimal(str(stats["usd"])) != money(expected_usd):
            raise OfflineFinanceConflict("Réconciliation impossible: total de caisse différent")
        if (stats["final_hash"] or None) != (final_entry_hash or None):
            raise OfflineFinanceConflict("Réconciliation impossible: empreinte finale différente")
        self.connection.execute(text("""
            UPDATE offline_finance_leases
               SET status='CLOSED',closed_at=now(),reconciled_count=:n,reconciled_cdf=:cdf,reconciled_usd=:usd,
                   final_entry_hash=:hash
             WHERE id=:id AND status IN ('ACTIVE','DRAINING')
        """), {"id": str(lease_id), "n": expected_count, "cdf": str(money(expected_cdf)),
                 "usd": str(money(expected_usd)), "hash": final_entry_hash})
        self.connection.execute(text("""
            UPDATE offline_receipt_tokens SET status='VOID',void_reason='Lease clôturé: reçu non utilisé'
             WHERE lease_id=:id AND status='AVAILABLE'
        """), {"id": str(lease_id)})

    def force_release(self, lease_id: UUID, *, actor_user_id: UUID, reason: str) -> None:
        if len(reason.strip()) < 10:
            raise ValueError("Motif de libération forcée obligatoire (10 caractères minimum)")
        pending = int(self.connection.execute(text("""
            SELECT count(*) FROM offline_payment_inbox WHERE lease_id=:id AND status='RECEIVED'
        """), {"id": str(lease_id)}).scalar_one())
        if pending:
            raise OfflineFinanceConflict("Libération forcée interdite: des paiements reçus restent non appliqués")
        row = self.connection.execute(text("""
            UPDATE offline_finance_leases
               SET status='FORCE_RELEASED',force_released_at=now(),force_released_by=:uid,force_release_reason=:reason
             WHERE id=:id AND status IN ('PREPARING','ACTIVE','DRAINING') RETURNING school_id
        """), {"id": str(lease_id), "uid": str(actor_user_id), "reason": reason.strip()}).first()
        if row is None:
            raise OfflineFinanceConflict("Lease non libérable")
        school_id = row._mapping["school_id"]
        # Point 2: the DB trigger quarantines ACTIVE charge authority instead of silently
        # returning it to another cashier. The incident itself is also persisted explicitly.
        self.connection.execute(text("""
            INSERT INTO offline_finance_incidents(school_id,lease_id,actor_user_id,incident_type,reason)
            VALUES(:sid,:lid,:uid,'FORCE_RELEASE',:reason)
        """), {"sid": str(school_id), "lid": str(lease_id), "uid": str(actor_user_id),
                 "reason": reason.strip()})
        self.connection.execute(text("""
            UPDATE offline_receipt_tokens SET status='VOID',void_reason=:reason
             WHERE lease_id=:id AND status='AVAILABLE'
        """), {"id": str(lease_id), "reason": 'Libération forcée: '+reason.strip()})

    # ------------------------------------------------------------------
    # Point 2 / V2 — multi-caissier partitionné par charge
    # ------------------------------------------------------------------
    def acquire_multi_writer_lease(self, *, school_id: UUID, cashier_user_id: UUID, device_id: UUID,
                                   cash_session_id: UUID, max_payments: int, max_cdf: str, max_usd: str,
                                   receipt_count: int, local_minutes: int):
        if receipt_count < 1 or receipt_count > max_payments:
            raise ValueError("receipt_count doit être compris entre 1 et max_payments")
        if local_minutes < 5 or local_minutes > 720:
            raise ValueError("Fenêtre locale offline autorisée: 5..720 minutes")
        # Only serialize the same device/session arm; other cashiers remain free to arm concurrently.
        self.connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"offline-finance-v2:{school_id}:{device_id}:{cash_session_id}"},
        )
        row = self.connection.execute(text("""
            INSERT INTO offline_finance_leases(
              school_id,cashier_user_id,device_id,cash_session_id,status,local_stop_at,
              max_payments,max_cdf,max_usd,protocol_version
            ) VALUES(:sid,:uid,:did,:cs,'PREPARING',now()+make_interval(mins=>:mins),:maxp,:cdf,:usd,
                     'AUTHORIZED_PARTITIONED_CASH_V2')
            RETURNING *
        """), {"sid": str(school_id), "uid": str(cashier_user_id), "did": str(device_id),
                 "cs": str(cash_session_id), "mins": local_minutes, "maxp": max_payments,
                 "cdf": str(money(max_cdf)), "usd": str(money(max_usd))}).first()
        if row is None:
            raise RuntimeError("Impossible de créer le lease multi-caissier")
        lease = self._lease(row)
        tokens: list[ReceiptToken] = []
        for _ in range(receipt_count):
            token = self.connection.execute(text("""
                INSERT INTO offline_receipt_tokens(school_id,lease_id,receipt_no)
                VALUES(:sid,:lid,next_offline_receipt_no(:sid)) RETURNING *
            """), {"sid": str(school_id), "lid": str(lease.id)}).first()
            if token is None:
                raise RuntimeError("Impossible de préallouer un reçu offline")
            tokens.append(self._token(token))
        return lease, tokens

    def reserve_charge_snapshots(self, lease_id: UUID, snapshots) -> None:
        lease_row = self.connection.execute(text("""
            SELECT school_id,status,protocol_version FROM offline_finance_leases WHERE id=:id FOR UPDATE
        """), {"id": str(lease_id)}).first()
        if lease_row is None or lease_row._mapping["status"] != "PREPARING":
            raise OfflineFinanceConflict("Les autorités de charge ne peuvent être réservées que pendant PREPARING")
        school_id = lease_row._mapping["school_id"]
        rows = list(snapshots)
        if not rows:
            raise OfflineFinanceConflict("Au moins une charge doit être attribuée à cette caisse offline")
        if len({x.charge_id for x in rows}) != len(rows):
            raise OfflineFinanceConflict("Charge dupliquée dans le lot d'autorité offline")
        for snap in rows:
            # Per-charge advisory lock closes the race before the partial unique index does.
            self.connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": f"offline-charge:{school_id}:{snap.charge_id}"},
            )
            occupied = self.connection.execute(text("""
                SELECT lease_id,status FROM offline_charge_reservations
                 WHERE school_id=:sid AND charge_id=:cid AND status IN ('ACTIVE','QUARANTINED') FOR UPDATE
            """), {"sid": str(school_id), "cid": str(snap.charge_id)}).first()
            if occupied is not None and str(occupied._mapping["lease_id"]) != str(lease_id):
                raise OfflineFinanceConflict("Charge déjà attribuée à une autre caisse offline")
            self.connection.execute(text("""
                INSERT INTO offline_charge_snapshots(
                  school_id,lease_id,charge_id,enrollment_id,student_id,currency,remaining_amount,charge_version
                ) VALUES(:sid,:lid,:cid,:eid,:stid,:currency,:remaining,:version)
                ON CONFLICT (lease_id,charge_id) DO UPDATE SET
                  enrollment_id=EXCLUDED.enrollment_id,student_id=EXCLUDED.student_id,currency=EXCLUDED.currency,
                  remaining_amount=EXCLUDED.remaining_amount,charge_version=EXCLUDED.charge_version,snapshotted_at=now()
            """), {"sid": str(school_id), "lid": str(lease_id), "cid": str(snap.charge_id),
                     "eid": str(snap.enrollment_id), "stid": str(snap.student_id),
                     "currency": snap.currency, "remaining": str(money(snap.remaining_amount)),
                     "version": snap.version})
            self.connection.execute(text("""
                INSERT INTO offline_charge_reservations(
                  school_id,lease_id,charge_id,currency,authorized_amount,consumed_amount,status
                ) VALUES(:sid,:lid,:cid,:currency,:amount,0,'ACTIVE')
                ON CONFLICT (lease_id,charge_id) DO NOTHING
            """), {"sid": str(school_id), "lid": str(lease_id), "cid": str(snap.charge_id),
                     "currency": snap.currency, "amount": str(money(snap.remaining_amount))})

    def activate_multi_writer_lease(self, lease_id: UUID) -> OfflineFinanceLease:
        row = self.connection.execute(text("""
            UPDATE offline_finance_leases l SET status='ACTIVE',activated_at=now()
             WHERE l.id=:id AND l.status='PREPARING'
               AND l.protocol_version='AUTHORIZED_PARTITIONED_CASH_V2'
               AND EXISTS (SELECT 1 FROM offline_charge_reservations r WHERE r.lease_id=l.id AND r.status='ACTIVE')
               AND EXISTS (SELECT 1 FROM offline_receipt_tokens t WHERE t.lease_id=l.id AND t.status='AVAILABLE')
             RETURNING l.*
        """), {"id": str(lease_id)}).first()
        if row is None:
            raise OfflineFinanceConflict("Lease V2 non activable: autorité de charge ou reçus manquants")
        return self._lease(row)

    def lock_lease_for_sync(self, lease_id: UUID) -> None:
        row = self.connection.execute(text("""
            SELECT id FROM offline_finance_leases
             WHERE id=:id AND status IN ('ACTIVE','DRAINING') FOR UPDATE
        """), {"id": str(lease_id)}).first()
        if row is None:
            raise OfflineFinanceConflict("Lease offline non synchronisable")

    def journal_checkpoint(self, lease_id: UUID):
        from edusync.modules.finance_offline.domain.multi_cashier import JournalCheckpoint
        row = self.connection.execute(text("""
            SELECT journal_seq,entry_hash FROM offline_payment_inbox
             WHERE lease_id=:id ORDER BY journal_seq DESC LIMIT 1
        """), {"id": str(lease_id)}).first()
        if row is None:
            return JournalCheckpoint()
        return JournalCheckpoint(last_seq=int(row._mapping["journal_seq"]), last_hash=row._mapping["entry_hash"])

    def received_command(self, *, school_id: UUID, operation_id: UUID):
        from edusync.modules.finance_offline.domain.multi_cashier import ReceivedCommandRecord
        row = self.connection.execute(text("""
            SELECT operation_id,idempotency_key,receipt_no,journal_seq,entry_hash,status,payment_id
              FROM offline_payment_inbox WHERE school_id=:sid AND operation_id=:op FOR UPDATE
        """), {"sid": str(school_id), "op": str(operation_id)}).first()
        if row is None:
            return None
        m = row._mapping
        return ReceivedCommandRecord(
            operation_id=UUID(str(m["operation_id"])), idempotency_key=m["idempotency_key"],
            receipt_no=m["receipt_no"], journal_seq=int(m["journal_seq"]), entry_hash=m["entry_hash"],
            status=m["status"], payment_id=None if m["payment_id"] is None else UUID(str(m["payment_id"])),
        )

    def assert_server_lease_limits(self, lease_id: UUID) -> None:
        lease = self.connection.execute(text("""
            SELECT max_payments,max_cdf,max_usd FROM offline_finance_leases WHERE id=:id FOR UPDATE
        """), {"id": str(lease_id)}).first()
        if lease is None:
            raise OfflineFinanceConflict("Lease introuvable")
        stats = self.connection.execute(text("""
            SELECT count(*) n,
                   COALESCE(sum(amount) FILTER(WHERE currency='CDF'),0) cdf,
                   COALESCE(sum(amount) FILTER(WHERE currency='USD'),0) usd
              FROM offline_payment_inbox WHERE lease_id=:id AND status IN ('RECEIVED','APPLIED')
        """), {"id": str(lease_id)}).first()._mapping
        m = lease._mapping
        if int(stats["n"]) > int(m["max_payments"]):
            raise OfflineFinanceConflict("Plafond de nombre d'encaissements offline dépassé côté serveur")
        if Decimal(str(stats["cdf"])) > money(m["max_cdf"]):
            raise OfflineFinanceConflict("Plafond CDF offline dépassé côté serveur")
        if Decimal(str(stats["usd"])) > money(m["max_usd"]):
            raise OfflineFinanceConflict("Plafond USD offline dépassé côté serveur")

    def consume_charge_reservations(self, command: OfflinePaymentCommand) -> None:
        for allocation in command.allocations:
            row = self.connection.execute(text("""
                UPDATE offline_charge_reservations
                   SET consumed_amount=consumed_amount+:amount
                 WHERE school_id=:sid AND lease_id=:lid AND charge_id=:cid AND status='ACTIVE'
                   AND currency=:currency AND consumed_amount+:amount <= authorized_amount
                 RETURNING id
            """), {"amount": str(money(allocation.amount)), "sid": str(command.school_id),
                     "lid": str(command.lease_id), "cid": str(allocation.charge_id),
                     "currency": command.currency}).first()
            if row is None:
                raise OfflineFinanceConflict("Autorité offline absente ou montant réservé dépassé pour cette charge")

    def resolve_quarantine(self, lease_id: UUID, *, actor_user_id: UUID, reason: str) -> None:
        self.connection.execute(
            text("SELECT resolve_offline_finance_quarantine(:lid,:uid,:reason)"),
            {"lid": str(lease_id), "uid": str(actor_user_id), "reason": reason.strip()},
        )



def command_to_params(command: OfflinePaymentCommand) -> dict:
    import json
    return {
        "sid": str(command.school_id), "lid": str(command.lease_id), "op": str(command.operation_id),
        "idem": command.idempotency_key, "did": str(command.device_id), "uid": str(command.cashier_user_id),
        "cs": str(command.cash_session_id), "token": str(command.receipt_token_id), "receipt": command.receipt_no,
        "student": str(command.student_id), "enrollment": str(command.enrollment_id),
        "currency": command.currency, "amount": str(money(command.amount)), "mode": command.mode, "seq": command.journal_seq,
        "payload": json.dumps(command.canonical_payload(), ensure_ascii=False), "prev": command.previous_entry_hash,
        "hash": command.entry_hash, "client_time": command.client_time,
    }
