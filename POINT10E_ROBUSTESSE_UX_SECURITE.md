# Point 10E — Robustesse réseau, UX, sécurité et socle formulaires

- Connectivité centralisée: ONLINE / DEGRADED / SUSPECTED_OFFLINE / OFFLINE / RECOVERING.
- Aucun basculement offline sur un échec isolé. OFFLINE exige des échecs répétés et une durée minimale; retour ONLINE confirmé par plusieurs succès.
- Retry borné + backoff + jitter. Mutations seulement si protégées par Idempotency-Key; aucune répétition aveugle.
- Health probe distinct de navigator.onLine.
- Topbar compacte reflète l'état réel sans message technique.
- Erreurs HTTP techniques masquées côté utilisateur; détails réservés au diagnostic.
- Formulaires: socle partagé + React Hook Form + Zod + resolvers; validation homogène progressive des écrans.
- Feedback UX: Sonner pour confirmations/erreurs uniformes; aucun window.alert ne doit subsister à terme.
- Auth réelle déjà présente: PyJWT, access JWT typé, iss/aud/exp/nbf/jti; mots de passe Argon2.
- Cache réel déjà présent: Redis tenant-scoped, TTL borné; jamais source de vérité Finance.
- Observabilité: structlog JSON + correlation ID par requête.

## Gates honnêtes
Les dépendances frontend ajoutées sont déclarées mais le build npm dépend de leur installation. La migration de chaque ancien formulaire vers React Hook Form/Zod et le remplacement de tous les alert() historiques est un chantier transversal à poursuivre; le socle est désormais unique. Les tests PostgreSQL/Redis live et le navigateur Windows restent au Point 11.

## Validation locale
- pytest: 322/322 PASS
- compileall backend: PASS
- build React: non exécuté, node_modules absent; les dépendances sont déclarées dans package.json et devront être installées au gate machine.
