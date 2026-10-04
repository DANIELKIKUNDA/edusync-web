# Gate — Point 4A Paramètres

## PASS local

- Addendum rôles Directeur des études / Directeur de discipline : PASS.
- Scope standard Secondaire obligatoire : PASS statique + tests.
- Runtime IAM relié au RBAC Point 3 : PASS tests.
- Modèle Paramètres PostgreSQL multi-école : PASS statique.
- RLS + FORCE RLS déclarés : PASS statique.
- Aucun auto-provisioning de classes/tarifs : PASS tests.
- Cycle année scolaire explicite : PASS tests.
- Tarif zéro interdit : PASS code + contraintes SQL.
- Déduplication tarif exact : PASS statique SQL.
- Cohérence tenant pour classe/tarif : PASS code.
- Idempotence / optimistic concurrency / audit-outbox sur API : PASS tests/inspection.
- 25 routes Settings exposées dans OpenAPI : PASS.
- pytest : 140 PASS / 0 FAIL.
- compileall Python : PASS.
- contrats JSON : PASS.
- Service Worker / JS : PASS syntaxe.
- TypeScript applicatif : PASS transpilation syntaxique (3 fichiers).

## NON DÉCLARÉ LIVE

- PostgreSQL réel + RLS A/B : à exécuter sur Docker/VPS.
- migrations 0009-0011 réelles : à exécuter sur PostgreSQL.
- `npm install && npm run build` : non exécuté ici faute de `node_modules` React/types.
- contrôle visuel navigateur 1366x768/mobile : certification utilisateur au Point 7/final.
- sauvegarde/restauration serveur réelle et documents riches : Point 5.

**Verdict : POINT 4A LOCAL PASS; LIVE CERTIFICATION PENDING.**
