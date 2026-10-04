# Point 11B — Atelier Pro : opérations sensibles réelles
Date : 2026-09-15
Version : 0.32.0-atelier-pro-11b

## Fermé localement
- Annuaire écoles : recherche, filtre, pagination et actions réelles.
- Suspension d'une école avec motif obligatoire, idempotence, audit et outbox.
- Réactivation d'une école avec idempotence, audit et outbox.
- Création de l'administrateur système initial depuis Atelier Pro.
- Mot de passe initial absent du payload d'idempotence et de l'audit.
- Accès/identités : recherche + pagination réelle.
- Audit plateforme : pagination keyset conservée.
- Diagnostics : actualisation depuis les données serveur.
- Confirmations sensibles via dialogue accessible ; aucun prompt/confirm/alert natif.

## Validation
- pytest : 376/376 PASS.
- Python compileall : PASS.
- Build frontend Vite/TypeScript : NON exécuté, node_modules absent dans cet environnement.

## Gates restant pour certification production
- PostgreSQL/Redis réels et tests de concurrence/recovery.
- Build frontend réel et recette navigateur/Windows.
- Tests offensifs et RLS cross-tenant réels.
- Notifications système Atelier Pro et supervision approfondie restent à industrialiser dans les points suivants.
