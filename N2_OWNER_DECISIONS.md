# N2 — Décisions du propriétaire

Ce document sépare ce que le propriétaire a décidé de ce qui reste ouvert. Aucune règle métier ouverte n'a été
inventée dans le code : quand une décision manque, la fonction n'est pas construite ou reste au comportement
existant, et le point est listé ici.

## 1. Décisions prises (2026-10-14, réponses en séance)

| # | Sujet | Décision | Mise en œuvre |
|---|-------|----------|---------------|
| D1 | Création d'un compte par l'école | **Mot de passe provisoire** généré par EduSync et montré une seule fois à l'administrateur (pas d'invitation par lien : elle supposerait un e-mail ou un SMS réel, indisponible localement) | `POST /access/members` ; le mot de passe n'est jamais enregistré dans la réponse idempotente : un rejeu renvoie `temporary_password: null` |
| D2 | Première connexion avec un mot de passe provisoire | **Changement obligatoire** avant toute session | connexion → étape `password_change_required` → `POST /auth/password/first-change` ; aucune session n'est ouverte par cette route |
| D3 | Adresse e-mail déjà utilisée (compte d'une autre école) | **Rattacher le compte** sans voir ni modifier son mot de passe ; l'école ne peut ni le renommer ni le réinitialiser (« Compte partagé ») | `_account_shared()` bloque renommage et réinitialisation |
| D4 | Réinitialisation par l'administrateur d'école | **Mot de passe provisoire + toutes les sessions coupées** | `POST /access/members/{id}/credentials-reset` ; refusée pour un compte partagé ou désactivé |

Décisions déjà prises avant le N2 et conservées : MFA des comptes plateforme (option B), confirmation par code pour
les actions sensibles, MFA dans les espaces école pour les comptes équipés, alerte de réinitialisation, avertissement
quand il reste moins de deux Managers (voir MFA_PLATFORM_OPTION_B_REPORT.md).

## 2. Règles appliquées sans décision nouvelle (déduites de l'existant)

| Règle | Fondement |
|-------|-----------|
| Désactiver un membre coupe ses sessions **dans cette école seulement** ; le compte reste valable ailleurs | multi-école déjà en place ; aucune autre lecture possible sans casser l'accès légitime à l'autre école |
| Anti-escalade limitée aux capacités de gouvernance (`access.*`) : on ne délègue pas plus de droits d'accès qu'on n'en détient | le rôle ADMIN_SYSTEME_ECOLE validé par le propriétaire (migration 0008) ne détient volontairement aucun droit financier mais doit pouvoir attribuer CAISSIER ; une règle stricte sur toutes les capacités contredirait ce rôle |
| Il reste toujours au moins un gestionnaire des accès actif | garde existante `_assert_managers_remain` |
| Une année active à la fois ; il faut clôturer l'année en cours avant d'en activer une autre | règle serveur existante ; l'écran l'explique au lieu d'afficher une erreur |
| Les cinq champs de terrain (nom, post-nom, prénom, sexe, classe) restent obligatoires ; l'école peut en exiger davantage, jamais moins | règle serveur existante du module Élèves |
| Désactiver une classe ou une option ne supprime rien et reste réversible | aucune route de suppression ; l'historique est conservé |

## 3. Décisions ouvertes (OWNER_DECISION)

| # | Question | Recommandation | Effet tant que rien n'est décidé |
|---|----------|----------------|----------------------------------|
| O1 | Faut-il imposer aussi le changement de mot de passe à l'**administrateur initial créé par la plateforme** (Atelier Pro) ? | Oui : même règle que D2, la plateforme connaît ce mot de passe | inchangé : l'administrateur initial garde le mot de passe saisi par la plateforme |
| O2 | Une classe qui a des **élèves inscrits** peut-elle être désactivée ? | Refuser côté serveur tant que des inscriptions actives existent, ou demander une confirmation renforcée qui affiche leur nombre | autorisé, après confirmation ; la classe n'est plus proposée pour les nouveaux tarifs, les élèves gardent leur inscription |
| O3 | Contenu des politiques **PAYMENT, BENEFITS, DOCUMENTS, BACKUP, COMMUNICATIONS** | Les définir module par module, au moment où un module les applique réellement | stockées par le serveur mais lues par aucun module, donc **sans écran** (afficher un réglage sans effet tromperait l'école) |
| O4 | **Invitation par lien** (e-mail ou SMS) au lieu du mot de passe provisoire | À rouvrir quand un fournisseur e-mail ou SMS réel sera configuré | BLOCKED_EXTERNAL ; D1 s'applique |
| O5 | **Groupes tarifaires des options** (`tariff_group_code`) : un tarif peut-il viser une option ? | À confirmer avec la grille réelle d'une école du secondaire | l'écran gère les options sans groupe tarifaire ; le champ reste vide |
| O6 | Droits de **réactivation d'une classe** : le serveur demande `settings.classes.rename` pour réactiver et `settings.classes.activate` pour désactiver | Utiliser `settings.classes.activate` dans les deux sens | l'écran suit le serveur : il ne montre le bouton qu'à qui a le droit correspondant |
