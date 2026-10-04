# Point 10H — robustesse, sessions persistantes, sécurité et performance

## Fermé dans le code
- Session appareil persistante et révocable : JWT d'accès court (15 min) + session opaque serveur longue durée, cookie HttpOnly/SameSite, rotation automatique du JWT, révocation explicite et révocation au changement de mot de passe. L'utilisateur ne doit pas ressaisir son mot de passe périodiquement sur un appareil autorisé.
- Administration Sync : état, appareils, enregistrement/révocation et lecture des conflits.
- Intendance : correction de stock signée INCREASE/DECREASE, création/état/historique des biens, inventaires physiques et validation des écarts justifiés.
- Communications : provider abstraction, adapter Orange configurable, mock dev, retries exponentiels bornés, terminal failure; aucune erreur fournisseur ne rollback une opération métier.
- Erreurs UI : suppression des affichages directs d'exception détectés; pipeline `friendlyError`.
- Performance : lazy loading existant + index des chemins chauds + scénario k6 + requêtes EXPLAIN/BUFFERS pour PostgreSQL.
- Sécurité : plan offensif live obligatoire; JWT/Argon2/RBAC/RLS/headers/rate limiting restent en place.

## Gates qui ne peuvent pas être honnêtement certifiés dans ce conteneur
- `npm install` a expiré; build TypeScript/Vite non certifié faute de node_modules.
- k6, PostgreSQL, Redis et Docker ne sont pas disponibles ici : aucune latence p95/p99 réelle, aucun EXPLAIN ANALYZE réel, aucun test de panne Redis, aucune concurrence PostgreSQL/RLS réelle ne peut être déclarée PASS.
- Aucun credential/provider SMS réel n'est fourni : adapter présent, livraison Orange réelle non certifiée.
- Les familles documentaires Finance marquées `DESKTOP_GOLDEN_REQUIRED` restent volontairement non promues : le code ne doit pas fabriquer une parité sans golden master Desktop brut.
- Les prompts natifs restants dans les workflows Personnel/Élèves sont un reliquat UX à remplacer par dialogues homogènes avant fermeture visuelle.
- La migration complète de tous les formulaires métier vers React Hook Form + Zod n'est pas encore totale; le socle est présent mais la certification 100% exige le build et une passe écran par écran.

## Validation locale
`pytest` et `compileall` sont les seules validations exécutables de façon fiable ici. Les gates live sont explicitement reportés, pas maquillés.
