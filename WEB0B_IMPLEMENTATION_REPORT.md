# EduSync WEB-0B — Idempotence & concurrence

Date : 2026-09-11

## Objet

WEB-0B durcit la fondation SaaS multi-école avant le portage des domaines métier Desktop. Le lot traite l'idempotence, la concurrence optimiste, la déduplication de synchronisation, les conflits offline et les hooks de verrouillage transactionnel financier.

## Invariants introduits

- `idempotency_registry` persistant avec unicité `(scope_key, idempotency_key)` et empreinte SHA-256 de la requête.
- même clé + même requête réussie : rejeu de la réponse sans deuxième effet métier ; même clé + payload différent : conflit.
- `version` sur les agrégats fondation (`schools`, `users`, `school_memberships`).
- contrat SQL `UPDATE ... WHERE version=:expected RETURNING version` pour concurrence optimiste.
- `sync_conflicts` pour enregistrer les conflits offline/non fusionnables.
- déduplication outbox (`deduplication_key`) et inbox (`operation_id`, plus idempotency key déjà unique par école).
- RLS des nouvelles tables tenant.
- transactions tenant utilisant `SET LOCAL app.current_school_id` via `set_config(..., true)`.
- hook `SELECT ... FOR UPDATE` explicitement réservé aux ressources financières sensibles et exécuté dans la transaction métier.
- Finance offline reste **fail-closed** : aucun paiement offline définitif n'est activé par WEB-0B.

## Doctrine Finance préparée

Le futur port Finance devra exécuter dans une même transaction PostgreSQL :

1. réservation idempotente ;
2. verrou des charges / session de caisse pertinentes ;
3. relecture et recalcul du solde serveur ;
4. validation des allocations ;
5. paiement ;
6. reçu ;
7. mouvement de caisse ;
8. audit append-only ;
9. événement outbox ;
10. commit unique.

Aucun merge automatique n'est autorisé pour un conflit financier.

## Limite de certification de ce lot

Les tests unitaires et statiques sont exécutables dans l'environnement présent. Le conteneur Docker/PostgreSQL n'est pas disponible dans cet environnement ; le probe `backend/scripts/g1_postgres_probe.py` est donc fourni pour la certification live sur le poste/VPS. **WEB-0B ne prétend pas encore que le Gate G1 PostgreSQL live est acquis.**

Le Desktop de référence et ses exports ne sont pas modifiés.
