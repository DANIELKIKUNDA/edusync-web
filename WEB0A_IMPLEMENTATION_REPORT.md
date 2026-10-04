# WEB-0A — Rapport d'implémentation

Ce lot crée une nouvelle fondation séparée du Desktop fourni. Aucun fichier de l'application Desktop ni aucune base SQLite n'est modifié.

## Livré

- monorepo `backend/`, `frontend/`, `infra/preservation` ;
- domaine `Platform` avec `School` et transitions de statut ;
- cas d'usage Atelier Pro : créer école, suspendre, réactiver, bootstrap administrateur école ;
- IAM foundation : user, membership, rôles et permissions ;
- audit append-only ;
- transactional outbox foundation ;
- notifications foundation ;
- contrat Sync avec idempotency key ;
- interdiction explicite du paiement offline définitif au stade WEB-0A ;
- migration PostgreSQL initiale + RLS tenant ;
- PWA React minimale avec page Atelier Pro ;
- IndexedDB outbox foundation ;
- Docker Compose VPS.

## Limite assumée

L'API WEB-0A utilise encore un repository mémoire et un header de développement pour démontrer le parcours Atelier Pro. **Ce garde n'est pas destiné à la production.** Le gate suivant doit brancher PostgreSQL, migrations, session tenant et JWT/IAM réel avant tout déploiement public.
