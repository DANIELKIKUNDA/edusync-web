# EduSync — doctrine performance & scalabilité (Point 10H6)

## Principe
La performance n'est pas certifiée par la présence d'index. Chaque index doit correspondre à un chemin de requête réel et être validé sur un volume représentatif avec `EXPLAIN (ANALYZE, BUFFERS)` et `pg_stat_statements`.

## Base PostgreSQL
- index composites commencent par le tenant (`school_id`) sur les tables métier ;
- index partiels pour files/états chauds (outbox non publiée, notifications non lues, affectations ouvertes) ;
- trigram GIN pour recherches `ILIKE '%terme%'` ;
- éviter la sur-indexation des tables à forte écriture ;
- surveiller scans séquentiels, index inutilisés, bloat, cache-hit, verrous et requêtes p95/p99.

## API
- toutes les listes volumineuses doivent être bornées et paginées ;
- plafond serveur explicite ;
- filtres appliqués en SQL, jamais après chargement massif ;
- payloads de liste limités aux colonnes nécessaires ;
- pagination par curseur à préférer pour historiques très profonds ; OFFSET reste acceptable pour annuaires scolaires modestes ;
- timeout, correlation-id et métriques par route ;
- cache uniquement pour read-models stables et toujours tenant-aware ; jamais cache partagé sans clé `school_id`.

## Scalabilité
Le monolithe modulaire peut être répliqué horizontalement derrière un reverse proxy. L'état partagé reste PostgreSQL/Redis/object storage. Les workers outbox/communications doivent être indépendants des processus API. Les sessions persistantes sont serveur-side et donc compatibles multi-instance.

## Gates avant production
1. Charger un dataset anonymisé représentatif (petite, moyenne, grande école + plusieurs écoles).
2. `ANALYZE` puis exécuter `performance/postgres-benchmark.sql`.
3. Capturer plans, buffers, rows, planning/execution time.
4. Exécuter k6 sur endpoints métier authentifiés, pas seulement `/health`.
5. Cibles initiales: erreurs <1%, GET métier p95 <500 ms et p99 <1000 ms sous charge nominale; mutations p95 <800 ms hors génération documentaire/provider externe.
6. Tester concurrence multi-caissier et saturation pool DB.
7. Réviser les index à partir des mesures, pas par intuition.
