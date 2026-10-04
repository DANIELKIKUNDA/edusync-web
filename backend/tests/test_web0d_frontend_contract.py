from pathlib import Path

TS = (Path(__file__).parents[2] / "frontend" / "src" / "offline" / "financeJournal.ts").read_text(encoding="utf-8")


def test_browser_requires_persistent_storage_for_cash_offline():
    assert "ensureDurableStorage" in TS
    assert "navigator.storage.persist" in TS
    assert "encaissement offline désactivé" in TS


def test_local_journal_has_unique_operation_idempotency_receipt_and_sequence_indexes():
    for name in ("operation", "idempotency", "receipt", "sequence"):
        assert f"createIndex('{name}'" in TS


def test_receipt_token_and_journal_append_are_one_indexeddb_transaction():
    assert "db.transaction([JOURNAL,META,TOKENS],'readwrite')" in TS
    assert "objectStore(JOURNAL).add(row)" in TS
    assert "status:'CONSUMED'" in TS


def test_local_charge_snapshot_prevents_cumulative_overpayment():
    assert "assertAllocationsAgainstFrozenBalances" in TS
    assert "Montant cumulé supérieur au solde figé" in TS


def test_local_cash_only_and_window_cutoff_are_enforced():
    assert "autorise uniquement CASH" in TS
    assert "Fenêtre offline terminée" in TS


def test_sync_can_send_full_journal_for_hash_chain_replay_validation():
    assert "allCashPayments" in TS
    assert "journalSeq" in TS
    assert "previousEntryHash" in TS
    assert "entryHash" in TS
