# Proposition de rôles plateforme « industriels » — NON ACTIVÉS — OWNER_DECISION

Ces rôles ne sont **pas** créés. Ils peuvent l'être en quelques minutes depuis Atelier Pro › Équipe
plateforme › Nouveau rôle (brouillon puis activation), ou rester inutilisés. Le choix appartient au propriétaire.

| Rôle proposé | Capacités | Usage | Risque principal |
|---|---|---|---|
| Support niveau 1 | `schools.read`, `health.read` | Répondre aux écoles, vérifier l'état | Lecture de l'annuaire des écoles |
| Support niveau 2 | N1 + `school_admin.bootstrap` | Réinitialiser l'administrateur d'une école bloquée | Prise de contrôle d'une école si abus (audité) |
| Chargé de déploiement | `schools.read`, `schools.create`, `school_admin.bootstrap` | Ouvrir les nouvelles écoles | Création d'écoles fictives (limitée à 30/h, auditée) |
| Responsable conformité | `schools.read`, `audit.read`, `audit.export` | Contrôles, réponses aux demandes officielles | Export de données d'audit (borné, audité) |
| Exploitation technique | `health.read`, `schools.read` | Surveillance | Faible |
| Communication | `schools.read`, `notifications.system.send` | Messages aux écoles | Diffusion massive (20/h, auditée) |
| Gouvernance des accès écoles | `schools.read`, `access.manage` | Gérer les rôles standard dans les écoles | Élévation dans une école (auditée) |

## Ce qui n'est pas proposé
* Un rôle délégant `platform.collaborators.manage` : réservé au Manager système (décision de sécurité de cette passe).
* La suspension d'école hors Manager : `schools.suspend` coupe toute une école ; à garder au Manager, sauf
  décision contraire.

## Options pour le propriétaire
1. Ne rien créer (seuls Manager système et Collaborateur plateforme existent).
2. Créer uniquement « Support niveau 1 » et « Exploitation technique » (lecture seule).
3. Créer tout ou partie du tableau, en brouillon d'abord, puis activer après relecture.

Conséquence commune : chaque attribution, retrait, suspension et réinitialisation est tracée dans l'audit, et
aucun de ces rôles ne donne accès aux données métier des écoles (aucune capacité SCHOOL possible).
