# Point 11D — Atelier Pro : Accès/RBAC et readiness école

- Fiche école réelle: identité, statut, membres, rôles et gates de préparation.
- Readiness progressive: identité, administrateur initial, année scolaire, classes, catalogue de frais. Aucun verrou global.
- Gouvernance accès: activation/désactivation d'une appartenance école et attribution d'un rôle standard actif.
- Permission critique dédiée `platform.access.manage`, accordée au `MANAGER_SYSTEME` par migration 0032.
- Mutations tenant-ciblées, verrouillées `FOR UPDATE` et auditées append-only.
- La désactivation d'une appartenance désactive ses assignments RBAC actifs; la réactivation ne restaure pas silencieusement d'anciens rôles.
- Validation locale: pytest + compileall. Build Vite non revendiqué sans node_modules.
