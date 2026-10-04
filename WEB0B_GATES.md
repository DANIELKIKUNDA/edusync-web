# WEB-0B — Gates Idempotence / Concurrence

## G1-CONCURRENCY-IDEMPOTENCY

Conditions de PASS final :

- [x] contrat idempotency key + hash canonique ;
- [x] unicité PostgreSQL déclarée ;
- [x] même clé / payload différent rejeté ;
- [x] rejeu réussi ne réexécute pas l'effet métier (test unitaire) ;
- [x] double-submit concurrent : un seul propriétaire logique (test thread-safe) ;
- [x] versioning optimiste déclaré ;
- [x] conflits offline persistables ;
- [x] outbox/inbox dédupliquées ;
- [x] RLS sur nouvelles tables tenant ;
- [x] Finance offline reste fail-closed ;
- [ ] probe PostgreSQL live exécuté sur Docker/VPS ;
- [ ] test RLS live École A ↔ École B avec rôle DB applicatif non privilégié ;
- [ ] test de deux transactions PostgreSQL concurrentes sur une même ressource financière réelle (sera finalisé lors du port Finance).

Verdict du présent artefact : **READY FOR LIVE G1 CERTIFICATION**, pas encore `G1 PASS`.
