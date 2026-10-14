# Droits dans l'école (RBAC) — certification N2

Date : 2026-10-14. Preuves : sonde réelle `certification/n2-20261014/n2_probe.py` → `n2-live.json` (**50/50 PASS**,
relancée le 2026-10-14 sur l'état final du code serveur), tests de contrat `backend/tests/test_n2_school_autonomy.py`,
suite complète `pytest` (589 tests verts).

## 1. Modèle

- Capacités fines (`capability_catalog`, migration 0006), regroupées en rôles. Rôles standard validés par le
  propriétaire (migration 0008), dont ADMIN_SYSTEME_ECOLE, CAISSIER… ; rôles propres à chaque école.
- Une **attribution** relie un membre de l'école à un rôle ; elle est toujours limitée à l'école (`school_id`),
  protégée par la sécurité au niveau des lignes de PostgreSQL (RLS forcée).
- Capacités de **gouvernance** : préfixe `access.` (gérer les membres, les rôles, les attributions).

## 2. Garanties et preuves

| Garantie | Mécanisme | Preuve (sonde N2) |
|----------|-----------|-------------------|
| L'école crée ses comptes elle-même, sans la plateforme | `POST /access/members`, droit `access.users.create` | « Création d'un membre par l'école : compte créé, rôle attribué, mot de passe provisoire affiché » |
| Le mot de passe provisoire n'est montré qu'une fois et n'est stocké nulle part en clair | réponse construite hors du registre d'idempotence ; jamais dans l'audit | « Double clic / réponse perdue : même membre, et le mot de passe n'est jamais rejoué » ; « Mot de passe provisoire absent du registre d'idempotence et de l'audit » |
| Aucune session tant que le mot de passe provisoire n'est pas remplacé | étape `PASSWORD` à usage unique, aucune émission de jeton | « Première connexion : aucune session avant d'avoir choisi son mot de passe » ; « Étape consommée : réutilisation refusée » ; « Ancien mot de passe provisoire refusé » |
| Un compte d'une autre école est rattaché, jamais pris en main | `_account_shared()` | « Adresse déjà utilisée dans l'école B → compte rattaché, aucun mot de passe affiché » ; « Compte partagé : réinitialisation … refusée (409) » ; « … changement de nom … refusé (409) » |
| Révocation **immédiate** | désactivation / réinitialisation incrémentent la version du compte ou de l'adhésion et révoquent les sessions | « Après réinitialisation : ancien jeton coupé immédiatement » ; « Désactivation : jeton en cours refusé immédiatement » ; « Désactivation : plus aucun espace à la connexion (403) » |
| Personne n'agit sur son propre compte | `_target()` refuse l'acteur lui-même | « Personne n'agit sur son propre compte (désactivation de soi → 403) » |
| Il reste toujours un gestionnaire des accès | `_assert_managers_remain` | test de contrat `test_deactivation_keeps_an_access_manager_and_ends_sessions_of_this_school` |
| **Anti-escalade** : on ne délègue pas de capacité de gouvernance qu'on ne détient pas | `_assert_can_delegate` sur création et modification de rôle, attribution, création de membre ; cible dont la gouvernance dépasse celle de l'acteur refusée | « Anti-escalade : un délégué ne donne pas le rôle d'administrateur qu'il n'a pas (403) » ; « … création d'un complice administrateur refusée (403) » ; « … aucun compte complice créé (transaction annulée) » ; « Le délégué peut transmettre un rôle qu'il détient entièrement » |
| Chaque droit est vérifié côté serveur | `_need(actor, capability)` en tête de route | « Le délégué ne peut pas réinitialiser un mot de passe (droit absent → 403) » |
| Tout est audité | actions `ACCESS_MEMBER_CREATED / ATTACHED / UPDATED / DEACTIVATED / ACTIVATED / CREDENTIALS_RESET`, rôles et attributions | « Journal : création, rattachement, modification, réinitialisation, désactivation, réactivation audités » |

## 3. Choix de conception à connaître

- L'anti-escalade porte sur les capacités **de gouvernance** (`access.*`) et non sur toutes les capacités : le rôle
  ADMIN_SYSTEME_ECOLE validé par le propriétaire ne détient volontairement aucun droit financier mais doit pouvoir
  attribuer le rôle CAISSIER. Une règle « on ne délègue que ce qu'on détient » sur toutes les capacités rendrait ce
  rôle inutilisable. L'administrateur ne peut pas pour autant s'attribuer les droits financiers : l'auto-action est
  refusée (voir N2_OWNER_DECISIONS.md §2).
- Le droit de réactiver une classe est `settings.classes.rename` côté serveur (O6, ouvert).

## 4. Interface

Accès & rôles (access.tsx) : liste des membres en premier sur téléphone, feuille de détail (rôles, renommer,
réinitialiser, désactiver ou réactiver), boutons absents ou inactifs pour un compte partagé, écran du mot de passe
provisoire à usage unique avec case de confirmation. Les boutons suivent les droits ; le serveur reste l'arbitre.

## 5. Verdict

**PASS LOCAL** pour l'administration des utilisateurs et des droits par l'école : création, rattachement,
réinitialisation, désactivation et réactivation, anti-escalade et révocation immédiate sont prouvés par la sonde
réelle. Points ouverts : O1 (mot de passe de l'administrateur initial), O6 (droit de réactivation des classes).
