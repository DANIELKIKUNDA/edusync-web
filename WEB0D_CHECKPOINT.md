# CHECKPOINT — EduSync Web 0.4.0 / WEB-0D

Date : 2026-09-11

## État

- Foundation multi-école / Atelier Pro : héritée de WEB-0C.
- Idempotence + concurrence : héritées et conservées.
- Finance Offline : protocole `EXCLUSIVE_SINGLE_WRITER_CASH_V1` implémenté.
- Validation locale : 79/79 tests PASS.
- Hash Python ↔ JavaScript : PASS.
- PostgreSQL live G1 : à exécuter.
- PostgreSQL live G2-A protocole offline : à exécuter.
- G2-B posting adapter vers le ledger Finance Web canonique : attend le portage Finance.
- Feature production Finance Offline : OFF par défaut et bloquée sans certification.

## Décision de reprise

Ne pas revenir au fail-closed permanent. Conserver le protocole WEB-0D. Lors du portage Finance, implémenter `OfflinePaymentPostingPort` avec la même transaction que charge/paiement/allocations/reçu/caisse/audit/outbox, puis fermer G2-B avant d'activer le feature flag.
