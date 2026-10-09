# Inventaire des rôles PLATFORM (Atelier Pro)

Source : base vierge provisionnée jusqu'à la migration 0055 (`edusync_closure_blank`), catalogue des capacités
et rôles standard. Aucun rôle n'est inventé ici.

## Capacités plateforme (12)

| Capacité | Libellé | Risque | Réservée | Écran / API qui l'exige |
|---|---|---|---|---|
| `platform.schools.read` | Voir les écoles de la plateforme | Moyen | non | Tableau de bord, Écoles, Accès écoles |
| `platform.schools.create` | Créer une école | Élevé | non | Écoles › Nouvelle école |
| `platform.schools.update` | Modifier l'identité technique d'une école | Élevé | non | (aucune route plateforme ne l'utilise encore : voir lacunes) |
| `platform.schools.suspend` | Suspendre une école | Critique | non | Écoles › Suspendre |
| `platform.schools.activate` | Activer une école | Élevé | non | Écoles › Réactiver |
| `platform.school_admin.bootstrap` | Créer/réinitialiser l'administrateur initial | Critique | non | Écoles › Créer admin |
| `platform.access.manage` | Gouverner appartenances et rôles standard des écoles | Critique | non | Fiche école › accès |
| `platform.collaborators.manage` | Gérer les collaborateurs de plateforme | Critique | **oui** | Équipe plateforme (comptes, rôles, attributions) |
| `platform.audit.read` | Consulter l'audit | Élevé | non | Journal d'audit |
| `platform.audit.export` | Exporter l'audit | Élevé | non | Journal d'audit › Exporter |
| `platform.health.read` | Voir l'état technique | Moyen | non | État du service |
| `platform.notifications.system.send` | Envoyer des notifications ciblées | Élevé | non | Notifications |

« Réservée » : jamais délégable dans un rôle personnalisé (contrôle API + déclencheur SQL, migration 0052).

## Rôles standard (PLATFORM_STANDARD)

| Code | Libellé | Statut | Capacités | Origine |
|---|---|---|---|---|
| `MANAGER_SYSTEME` | Manager système | ACTIF | les 12 | Décision du propriétaire (migration 0007) |
| `COLLABORATEUR_PLATEFORME` | Collaborateur plateforme | ACTIF | `schools.read`, `health.read`, `audit.read` | Rôle existant (point 11) |

Aucune capacité n'a été ajoutée à un rôle standard pendant cette passe (règles validées inchangées).

## Rôles personnalisés (PLATFORM_CUSTOM)
Nouveauté de cette passe : créés en **brouillon** par un Manager, activés explicitement, archivables, clonables.
Ils ne contiennent que des capacités plateforme détenues par celui qui les crée, jamais la capacité réservée,
jamais une capacité école (déclencheur SQL). Un rôle en brouillon ou archivé ne donne aucun droit.
La base vierge n'en contient aucun : leur création est une décision d'exploitation.

## Menu calculé par le serveur
`GET /api/v1/platform/team/me` renvoie le menu selon les capacités effectives (union des rôles actifs) :

| Entrée | Capacité |
|---|---|
| Tableau de bord, Écoles, Accès écoles | `platform.schools.read` |
| Équipe plateforme | `platform.collaborators.manage` |
| Notifications | `platform.notifications.system.send` |
| Journal d'audit | `platform.audit.read` |
| État du service | `platform.health.read` |

Preuve : `certification/n0-n1-20261007/team-live.json` (Manager : 7 entrées ; rôle Support : 4 entrées).

## Lacune constatée
`platform.schools.update` existe au catalogue mais aucune route plateforme ne modifie l'identité d'une école
après création (c'est l'administrateur de l'école qui le fait dans Paramètres). Voir
`SCHOOL_ONBOARDING_GAP_REPORT.md`.
