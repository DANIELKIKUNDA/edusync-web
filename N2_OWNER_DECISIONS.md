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

## 4. Suite des décisions ouvertes (décisions du propriétaire du 2026-10-14, appliquées)

La section 3 est conservée pour la trace. Toutes ses questions ont reçu une réponse après la comparaison avec le golden
master Desktop (N2_BUSINESS_POLICY_BACKEND_FRONTEND_AUDIT.md §6 à §9) :

| # | Décision | Statut |
|---|----------|--------|
| O1 | Le premier `ADMIN_SYSTEME_ECOLE` choisit son mot de passe avant toute session ; le mot de passe provisoire ne sert qu'à cette étape | appliqué, sondé |
| O2 | Copier le Desktop : pause autorisée avec élèves (qui restent comptés et visibles), archivage seulement si la classe est vide | appliqué, class_status_probe 21/21 |
| O3 | Parité des Paramètres dont dépend la Finance avant le N3 ; sauvegardes = plateforme (`NOT_APPLICABLE_IN_SAAS`) ; communications = `WEB_EXTENSION` | lots L1 à L7 livrés ; N2_SETTINGS_PARITY_13_RUBRIQUES.md |
| O4 | Inchangé (BLOCKED_EXTERNAL) | — |
| O5 | Copier le Desktop : groupes Humanités générales / techniques / Autre, le tarif de classe le plus précis l'emporte | appliqué, tariff_rules_probe 36/36 |
| O6 | Le changement d'état demande le droit d'activation ; le renommage est séparé | appliqué, sondé |
| L6 | Plan anticipé ≠ fonds anticipé ; plans copiés du Desktop ; ancien mécanisme Web retiré de la caisse sans suppression | appliqué, anticipation_probe 30/30 |

Questions encore ouvertes (ne bloquent pas le N2) :

1. Quel rôle standard reçoit `finance.anticipation_plans.manage` ? Au Desktop : ADMIN et DIRECTION. Tant que rien n'est
   décidé, aucun rôle standard ne peut créer de plan (les sondes utilisent un rôle de recette).
2. Changement de classe d'un élève qui a déjà des frais : le Web copie le Desktop (refus). Une règle de transfert
   financier différente reste à décider si elle est voulue.
