# N2 — Inventaire : administration, configuration et autonomie d'une école

**Date** : 14 octobre 2026 · **SHA de départ N2** : `888bb0d` (code certifié `bc2344c`, étiquette
`n0-n1-mfa-decisions-local-certified-2026-10-14`) · `git status` propre, `main` = `origin/main`.
**Méthode** : lecture du code (backend, frontend, migrations, catalogue de capacités) + audit visuel réel de
l'administrateur de l'école A à 390 px et 1280 px (`certification/n2-20261014/n2_audit.mjs`, captures `audit-*.png`,
mesures `audit-metrics.json` : aucune erreur de console, aucun défilement horizontal de page).

Légende : **EXISTANT** (fonctionne, à certifier) · **PARTIEL** (incomplet ou UX insuffisante) · **ABSENT** ·
**À CONFIRMER** · **OWNER_DECISION**.

## 1. Parcours cible N2

Plateforme crée l'école → premier `ADMIN_SYSTEME_ECOLE` → identité → année → structure → inscriptions → finances →
documents/préférences → utilisateurs/rôles → école prête pour N3.

| Étape | Backend | Interface | Statut |
|---|---|---|---|
| Création école + administrateur initial (plateforme) | `POST /platform/schools`, `/bootstrap-admin` (certifié N1, step-up) | Atelier Pro | EXISTANT |
| Première connexion de l'administrateur | `/auth/login` AUTO | Écran de connexion | EXISTANT ; pas d'accueil guidé (voir §8) |
| Identité de l'école | `PATCH /settings/identity` (If-Match, idempotence, audit) | Paramètres › École & identité | PARTIEL (champ « URL du logo » libre ; logo réel envoyé ailleurs) |
| Année scolaire | `/settings/academic-years` (+activate/close/archive/reopen/copy-configuration) | Paramètres › Années | PARTIEL (clôture sans confirmation, formulaire prérempli d'une année existante) |
| Structure académique | sections, options, classes (`PUT/POST`) | Paramètres › Structure & classes | PARTIEL (options absentes de l'UI, pas d'édition/désactivation de classe) |
| Paramètres d'inscription | `/settings/policies/{kind}` | aucun écran | ABSENT (UI) |
| Paramètres financiers | fee-types, tariffs, contributions, products | Paramètres (4 onglets) | PARTIEL |
| Documents / branding | `/documents/branding/logo`, catalogue, historique | Documents | EXISTANT (logo à relier à l'identité) |
| **Utilisateurs de l'école** | **aucune route** | **aucun écran** | **ABSENT** (voir §6) |
| Rôles SCHOOL | `/access/*` (catalogue, rôles, membres, scopes, journal, attribution, retrait, archive) | Accès & rôles | EXISTANT / PARTIEL (mobile) |
| Personnel (fiches RH) | `/personnel/*` (25 routes) | Personnel | EXISTANT (N2 : seulement le lien fiche ↔ compte) |
| Sessions / appareils | `/auth/sessions`, revoke | Sécurité et appareils | EXISTANT |
| Audit école | `/access/journal`, `/audit` | Accès & rôles › Journal | EXISTANT |

## 2. Routes N2 (backend)

* **settings** (34) : overview, reference-catalog, identity ; academic-years (selector, list, create, update,
  copy-configuration, activate, close, archive, reopen) ; sections, options, classes (selector, list, create,
  update) ; fee-types, tariffs, contributions, products (list, create, update) ; policies/{kind} (get, put).
* **access** (10) : catalog, roles, members, scope-options, journal ; roles create/update/archive ; member role
  assignment ; assignment revoke.
* **personnel** (25) dont access-links (lier/délier une fiche du personnel à un compte **existant**).
* **documents** (8) : catalog, storage status, branding/logo (PUT/GET), history, open.
* **setup** (2) : statut, premier Manager (plateforme).

## 3. Écrans, onglets, dialogues (frontend)

| Écran | Composants | Statut UX |
|---|---|---|
| Coquille (desktop) | barre latérale ouverte + grande ligne « Réduire le menu » en bas | PARTIEL (mandat §19 : bouton iconique, mode rail, survol temporisé, épinglage) |
| Coquille (mobile) | barre du bas 5 entrées (Accueil, Élèves, Finance, Documents, Menu) + tiroir | EXISTANT ; le tiroir reste ouvert si l'on repasse en largeur bureau ; Paramètres/Accès seulement dans « Menu » |
| Accueil | KPI centrés, encaissement rapide | EXISTANT (KPI conformes à la règle icône-valeur-libellé) |
| Paramètres | 8 onglets latéraux (desktop) / **barre d'onglets horizontale tronquée** (mobile) | PARTIEL : 3 onglets visibles sur 8 à 390 px, aucun indice qu'il en reste ; formulaires au-dessus des listes |
| Paramètres › Années | formulaire de création toujours ouvert, liste, boutons d'état | PARTIEL : « Clôturer » sans confirmation, dates ISO brutes |
| Paramètres › Structure | puces de sections, 2 listes déroulantes sans libellé visible, tableau des classes | PARTIEL : options absentes, pas d'édition/désactivation, pas d'état vide guidé |
| Paramètres › Tarifs | formulaire 4 champs + tableau | PARTIEL : montants non formatés (`1500000.05 CDF`), tableau sur mobile |
| Paramètres › Identité | 7 champs + « URL du logo » | PARTIEL : téléphone sans `inputmode=tel`, logo en URL libre |
| Accès & rôles | 4 KPI, garde-fous, onglets Membres/Rôles/Journal, liste de 32 membres | PARTIEL : **aucun ajout de membre**, liste non paginée (6 000 px sur téléphone), bouton « Attribuer » pleine largeur par ligne, retrait de rôle par petite croix |
| Personnel | registre, fiches | EXISTANT (hors cœur N2) |

## 4. Stack formulaires / validation

React Hook Form + Zod déjà présents (`package.json`, `login.tsx`, `App.tsx`) : **standard conservé**, aucune
bibliothèque concurrente à ajouter. Le backend (Pydantic, contraintes SQL, RLS) reste l'autorité.

## 5. Capacités / scopes

258 capacités, rôles standard approuvés (migrations 0006–0011, 0044), rôles personnalisés, scopes
école/cycle/section/classe, exceptions temporaires, garde-fous (personne ne modifie ses propres droits, aucun droit
plateforme, toujours un gestionnaire des accès, journal). **EXISTANT**, à re-certifier sur deux écoles jumelles.

## 6. Écart majeur : gestion des utilisateurs de l'école — ABSENT

Le rôle `ADMIN_SYSTEME_ECOLE` (décision propriétaire, migration `0008`) détient `access.users.create`,
`access.users.update`, `access.users.activate`, `access.users.credentials.reset`, `access.users.read`,
`access.users.pin.self_change` — **aucune n'a de route ni d'écran**. Seule la plateforme crée des comptes
(`BootstrapSchoolAdmin`). Conséquence : **l'école ne peut pas s'administrer seule** (créer le compte d'un caissier,
désactiver un départ, débloquer un mot de passe oublié). Critère de fermeture N2 non atteignable en l'état.
La règle (qui a le droit) est documentée ; les modalités ne le sont pas → OWNER_DECISION (§9).

## 7. Autres constats

| # | Constat | Classement |
|---|---|---|
| 1 | Clôture d'année scolaire en un clic, sans confirmation (action lourde) | FUNCTIONAL_FIX / UX_FIX |
| 2 | « URL du logo » libre dans l'identité, alors que le logo est stocké de façon sûre via Documents (`branding/logo`, contrôle du contenu) | SECURITY_FIX (surface inutile) / UX_FIX |
| 3 | Paramètres d'inscription (`policies`) sans écran | UX_FIX (contenu exact des politiques : À CONFIRMER) |
| 4 | Options (section/option) sans écran | UX_FIX |
| 5 | Montants non formatés, dates ISO brutes | UX_FIX |
| 6 | Tiroir mobile resté ouvert au passage en largeur bureau | UX_FIX |
| 7 | Liste des membres non paginée, sans recherche côté serveur, 32 lignes = 6 000 px sur téléphone | UX_FIX / PERFORMANCE_FIX |
| 8 | Sidebar desktop : grande ligne « Réduire le menu » | UX_FIX (§19 du mandat) |
| 9 | Pas d'accueil guidé de l'administrateur au premier accès (écart #4 du rapport N1) | UX_FIX |
| 10 | Multi-tenant N2 (écoles jumelles A/B, UUID devinés, fichiers, exports) | à certifier |

## 8. Onboarding

`overview.readiness` calcule déjà des points « Prêt / À compléter / À confirmer » sans bloquer globalement : base
saine, à transformer en parcours guidé (aucune donnée fictive créée). Détail : `SCHOOL_ONBOARDING_GAP_REPORT.md`
(mis à jour pendant N2).

## 9. OWNER_DECISION nécessaires avant d'implémenter §6

1. **Création d'un compte par l'école** : mot de passe provisoire généré et transmis par l'administrateur (comme la
   plateforme aujourd'hui), ou invitation (lien) — l'invitation suppose un e-mail/SMS réel (BLOCKED_EXTERNAL).
2. **Changement du mot de passe provisoire à la première connexion** : imposé ou non.
3. **Réinitialisation des identifiants** par l'administrateur d'école : mot de passe provisoire + sessions coupées.
4. **Compte déjà existant** (même e-mail dans une autre école) : le rattacher (sans voir ni changer son mot de passe)
   ou refuser.
5. **Désactivation** d'un membre : coupe ses sessions de cette école seulement (le compte reste valable ailleurs).
