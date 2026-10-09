# Écarts d'onboarding d'une école — rapport N1

Parcours réel aujourd'hui : Manager → Nouvelle école → administrateur initial → l'administrateur se connecte
(sans code établissement) → Paramètres (année, sections, classes, frais, tarifs, logo) → rôles du personnel.

| # | Écart | Impact | Classement | Options |
|---|---|---|---|---|
| 1 | Pas de réinitialisation du **mot de passe** d'un administrateur d'école par la plateforme (le bootstrap ne touche pas au mot de passe d'un compte existant) | Un administrateur qui a perdu son mot de passe dépend d'un autre administrateur de son école, ou d'un nouvel administrateur nommé par la plateforme | OWNER_DECISION | A. Ajouter « Réinitialiser le mot de passe de l'administrateur » (capacité `school_admin.bootstrap`, motif, audit, sessions coupées). B. Garder la règle actuelle (la plateforme ne touche jamais aux mots de passe des écoles) et nommer un nouvel administrateur. |
| 2 | `platform.schools.update` sans route : la plateforme ne corrige pas le nom/contacts d'une école après création | Faute de frappe à la création corrigée par l'école elle-même (Paramètres) | UX_FIX (petit) | Ajouter « Modifier l'identité » dans la fiche école, auditée avant/après. |
| 3 | Pas d'envoi automatique des identifiants à l'administrateur (e-mail/SMS) | Le Manager transmet le mot de passe provisoire par un canal sûr | BLOCKED_EXTERNAL (pas de fournisseur e-mail/SMS réel) | Brancher un fournisseur au déploiement ; garder le changement de mot de passe à la première connexion (non imposé aujourd'hui → OWNER_DECISION). |
| 4 | Pas d'assistant « première configuration » côté école au premier login | L'administrateur découvre Paramètres seul (l'écran de préparation affiche déjà les points à compléter) | UX_FIX | Assistant guidé en 5 étapes au premier accès. |
| 5 | Pas de mise hors service définitive (`DISABLED`) depuis l'Atelier Pro | Une école fermée reste « suspendue » | OWNER_DECISION | Définir la procédure d'archivage (durée de conservation, export des données). |
| 6 | Doublons d'écoles de noms proches (codes différents) non détectés | Risque d'école fictive en double | OWNER_DECISION | Alerte de similarité de nom à la création. |

Aucun de ces écarts ne contourne la sécurité : ce sont des fonctions absentes, documentées, non simulées.
