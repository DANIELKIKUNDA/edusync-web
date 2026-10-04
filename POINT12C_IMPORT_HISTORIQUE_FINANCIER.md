# Point 12C — Import / reprise historique financière

## Doctrine
Une ancienne preuve de paiement n'est jamais rejouée comme un encaissement courant. La reprise crée une régularisation hors caisse rattachée à l'obligation financière correspondante. Elle ne crée ni `finance_payments`, ni mouvement de caisse, ni nouveau reçu EduSync.

## Flux
XLSX/CSV → analyse/staging → résolution élève + année + frais + période + devise → contrôle du reste dû → détection des références déjà reprises → prévisualisation → confirmation explicite → exécution atomique auditée.

Une erreur bloque tout le lot. L'absence de référence historique est un avertissement. Un montant supérieur au reste dû est une erreur. Les dates historiques sont conservées.

## Sécurité
Permissions dédiées `migration.finance_history.analyze` et `migration.finance_history.execute`, exécution CRITICAL/server-only, Idempotency-Key obligatoire, verrou `FOR UPDATE`, tables FORCE RLS, audit append-only, outbox, ledger de provenance.
