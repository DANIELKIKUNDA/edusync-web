# Point 10H10 — Redis / Outbox / reprise après panne

## Fermetures locales
- PostgreSQL reste la source de vérité de l'outbox transactionnelle.
- Publisher outbox dédié avec claim `FOR UPDATE SKIP LOCKED`, lease expirante et token de traitement.
- Redis n'est jamais utilisé comme stockage durable de l'état métier.
- Un échec Redis conserve l'événement PostgreSQL non publié, avec retry exponentiel borné.
- Dead-letter après épuisement des tentatives, sans suppression silencieuse.
- Enveloppe Redis porte l'identifiant immuable `event_id`; les consommateurs doivent dédupliquer cet identifiant (at-least-once).
- Worker Communications récupère les livraisons dues directement depuis PostgreSQL même si le hint Redis est perdu.
- Appel fournisseur SMS exécuté hors transaction/verrou PostgreSQL.
- Claims concurrents protégés par `SKIP LOCKED` + `processing_token` + `locked_until`.
- Index partiels dédiés au travail dû outbox et communications.

## Gate live restant
Ces garanties sont certifiées statiquement/unitairement ici. Les scénarios réels Redis/PostgreSQL restent à exécuter au Point 11 : kill -9 entre LPUSH/ACK, coupure Redis, redémarrage worker, concurrence multi-workers, saturation, latence et vérification d'absence de perte. La sémantique est at-least-once : un doublon de transport est acceptable, une perte ne l'est pas; les consommateurs doivent être idempotents par `event_id`.
