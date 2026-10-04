# Point 11F — Atelier Pro / fermeture globale locale

## Portée certifiée localement
- Cockpit plateforme branché sur PostgreSQL.
- Annuaire des écoles: recherche, pagination, création, suspension/réactivation, bootstrap admin, fiche école.
- Accès/RBAC: recherche, appartenances, activation/désactivation, attribution/retrait des rôles standards, révocation des sessions école lors de la désactivation.
- Readiness progressive: identité minimale, admin initial, année scolaire, classes, catalogue des frais. Aucun verrou global.
- Notifications système internes persistées et auditées.
- Audit plateforme append-only avec pagination keyset.
- Diagnostics réels PostgreSQL/outbox/Sync/sessions/communications.
- Surfaces sensibles permissionnées; mutations de gouvernance auditées.
- Aucun token d'accès persisté dans localStorage; restauration par cookie HttpOnly de session persistante.
- Aucun menu Atelier Pro fictif/inactif.

## Hors certification locale
- Build Vite/TypeScript réel si node_modules absent.
- PostgreSQL/RLS réel multi-tenant, Redis multi-process, Docker/VPS, navigateur Windows, k6, tests offensifs dynamiques et fournisseur SMS réel.
- Les dépendances frontend marquées `latest` restent un gate de reproductibilité à traiter avec un lockfile/install réel; aucune version n'est inventée ici.
