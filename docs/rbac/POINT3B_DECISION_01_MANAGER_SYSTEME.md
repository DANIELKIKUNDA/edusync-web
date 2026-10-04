# Point 3B — Décision 01 : Manager système

Statut : **VALIDÉE ET VERROUILLÉE PAR DANIEL — 2026-09-11**

## Principe
Le Manager système agit au niveau **Atelier Pro / plateforme**. Il n'obtient aucun accès métier à une école par simple effet de son rôle plateforme. Toute intervention métier dans une école exige une affectation école distincte ou un futur workflow de support exceptionnel audité.

## Capacités finales
- `platform.schools.read` — Voir les écoles de la plateforme
- `platform.schools.create` — Créer une école
- `platform.schools.update` — Modifier l’identité technique d’une école
- `platform.schools.activate` — Activer une école
- `platform.schools.suspend` — Suspendre une école
- `platform.school_admin.bootstrap` — Créer/réinitialiser l’administrateur initial d’une école
- `platform.health.read` — Voir l’état technique des écoles
- `platform.audit.read` — Consulter l’audit de plateforme
- `platform.audit.export` — Exporter l’audit de plateforme
- `platform.notifications.system.send` — Envoyer des notifications système ciblées aux écoles/utilisateurs

Total final : **10 capacités Atelier Pro**.

## Invariant de sécurité
L’envoi d’une notification système est `SERVER_ONLY`, audité et ne donne aucun accès aux données métier des écoles. La permission permet d’entrer dans le use case ; elle ne contourne ni ciblage, ni validation, ni audit.
