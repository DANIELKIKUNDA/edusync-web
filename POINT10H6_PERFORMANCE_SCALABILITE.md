# Point 10H6 — Performance & scalabilité

Cette passe traite la performance comme un contrat mesurable et non comme une simple présence d'index.

## Réalisé
- migration `0028_scalability_query_indexes.sql` fondée sur les chemins de requête réels ;
- index tenant-aware pour recherches annuaires élèves/familles/personnel, inscriptions, audit, intendance et Manager système ;
- `pg_trgm` + `btree_gin` pour les recherches `ILIKE '%...%'` sans abandonner l'isolation logique par école ;
- benchmark PostgreSQL enrichi sur élèves, inscriptions, paiements, outbox, audit et mouvements de stock ;
- doctrine API : pagination bornée, filtres SQL, payloads limités, cursor pagination pour historiques profonds, cache tenant-aware seulement ;
- doctrine de scalabilité horizontale : API stateless, PostgreSQL/Redis/object storage partagés, workers indépendants ;
- objectifs initiaux p95/p99 documentés.

## Validation locale
- `pytest -q`: 344/344 PASS.
- `python -m compileall -q src`: PASS.

## Gates réels non simulés
- PostgreSQL n'est pas disponible dans ce conteneur : aucun `EXPLAIN ANALYZE` réel n'est déclaré PASS.
- k6/Redis/Docker ne sont pas disponibles ici : aucune charge réelle n'est déclarée certifiée.
- les index devront être révisés avec `pg_stat_statements`, plans, buffers, cache hit, verrous et volumes représentatifs.

## Suite
Après fermeture des gates École disponibles localement, le chantier doit basculer sur l'industrialisation complète du niveau **Manager système / Atelier Pro** : shell, dashboard plateforme, annuaire écoles paginé/recherchable, provisioning/readiness, administration, audit plateforme, diagnostics et supervision, avec les mêmes exigences UX/performance/sécurité que le niveau École.
