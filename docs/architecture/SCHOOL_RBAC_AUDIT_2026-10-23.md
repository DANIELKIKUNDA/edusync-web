# Audit du modèle rôles / permissions / interface — niveau École (23/10/2026)

Audit **sans modification de code**. Sources : code backend et frontend (commit 4742b94), migrations 0006 à 0084,
`contracts/CAPABILITY_REGISTRY.json`, `contracts/POINT3B_ROLE_DECISIONS_FINAL.json`, et l'état **réel** d'une base
provisionnée par toutes les migrations (stack locale, tables `capability_catalog`, `rbac_roles`,
`rbac_role_capabilities`, `rbac_assignment_scopes`).

Convention : « capacité » = permission atomique (`students.read`). « Rôle » = ensemble nommé de capacités.

---

## 1. État actuel — ce qui est réellement appliqué

Le socle est **meilleur que ce que l'écran Administrateur école laisse penser**. Le moteur est déjà orienté capacités :

| Élément | Réalité aujourd'hui | Fichier |
|---|---|---|
| Catalogue | Table `capability_catalog` : **288 capacités** (272 école, 16 plateforme), avec domaine, risque, politique hors connexion, audit, portées | migrations 0006 et suivantes |
| Rôles standards | 11 rôles école + 2 rôles plateforme, `school_id NULL`, **immuables** (`kind=SCHOOL_STANDARD`) | 0008, 0009, 0044, 0068… |
| Rôles propres à l'école | `SCHOOL_CUSTOM`, créés en **clonant** un rôle standard puis en ajoutant/retirant des capacités | `access/api/router.py` |
| Affectation | `rbac_assignments` (membre × rôle × validité) + `rbac_assignment_scopes` (SCHOOL / SECTION / CLASS) | 0006 |
| Exceptions | `rbac_exception_grants` : octroi **individuel, temporaire, additif** | 0006, `postgres_authorization.py` |
| Calcul des droits | À **chaque requête**, rechargés depuis PostgreSQL (jamais depuis le jeton) : union des capacités des rôles actifs | `bootstrap/dependencies.py:145` |
| Contrôle backend | `actor.require(cap)` / `_need(actor, cap)` dans chaque routeur ; `scope_allows` pour les portées dans 6 modules | `shared/application/context.py` |
| Anti-escalade | Personne ne délègue une capacité de **gouvernance des accès** qu'il ne détient pas ; un gestionnaire des accès doit toujours rester | `access/api/router.py:450`, `_assert_managers_remain` |
| Isolation | RLS PostgreSQL FORCE par école, indépendante des capacités | 0006 et suivantes |
| Audit | Création/modification/archivage de rôle, affectation, révocation : journalisés | `access/api/router.py` |

**Conclusion** : le moteur backend est sain (capacités, union, RLS, rechargement à chaque requête, anti-escalade).
Les défauts sont surtout : (a) la **personnalisation par école** passe par un clonage qui fige les rôles,
(b) l'**interface École** ne s'appuie pas sur un contrat serveur (menus et tableau de bord devinés côté client),
(c) des **écarts** entre le contrat écrit et la base réelle, (d) un **shell École** en retard sur la Plateforme.

---

## 2. Rôles existants (base réelle)

| Code | Libellé | Capacités (base) | Capacités (contrat JSON) | Portée exigée | Remarque |
|---|---|---|---|---|---|
| ADMIN_SYSTEME_ECOLE | Administrateur système école | 88 | 88 | École | Créé par la plateforme. Accès, paramètres, synchronisation ; aucun métier opérationnel |
| PROMOTEUR | Promoteur | 115 | 108 | École | Gouvernance en lecture : voir, suivre, imprimer, exporter |
| GESTIONNAIRE | Gestionnaire | 131 | 118 | École | Gouvernance + autorité supérieure finance (annulations, décisions) |
| RESPONSABLE_FINANCE | Responsable chargé des finances | 69 | 67 | École | Contrôle financier, pas d'encaissement |
| PREFET_ETUDES | Préfet des études | 93 | 84 | **Section** (Secondaire) | Chef de section |
| DIRECTION_SECTION | Directeur / Directrice de section | 93 | 84 | **Section** (Primaire / Maternelle) | Mêmes pouvoirs que le Préfet |
| DIRECTEUR_ETUDES | Directeur des études | 42 | 45 | **Section** (Secondaire) | Pas de finance par défaut |
| DIRECTEUR_DISCIPLINE | Directeur de discipline | 38 | 41 | **Section** (Secondaire) | Communication parents |
| CAISSIER | Caissier | 101 | 92 | École | Inscription + encaissement, sa propre caisse |
| SECRETARIAT | Secrétariat | 32 | 24 | École | Production documentaire |
| INTENDANT | Intendant | 29 | 29 | École | Stocks, biens, inventaires |
| MANAGER_SYSTEME | Manager Système (plateforme) | 18 | 14 | Plateforme | Hors périmètre école |
| COLLABORATEUR_PLATEFORME | Collaborateur plateforme | — | — | Plateforme | Hors périmètre école |

Blueprints prévus mais non créés : `ASSISTANT_PROMOTEUR` (clone de Promoteur).
**Absent** : aucun rôle **Enseignant**, et aucun domaine **Académique** (notes, évaluations, bulletins, emploi du temps)
n'existe dans le catalogue. Voir §9.

---

## 3. Capacités existantes (272 école), par domaine

| Domaine | Nb | Exemples / groupes |
|---|---|---|
| Utilisateurs & accès | 11 | `access.users.{read,create,update,activate,credentials.reset,pin.self_change}`, `access.roles.{read,manage}`, `access.permissions.assign`, `access.scopes.assign`, `access.grants.exception` |
| Audit | 4 | `audit.school.{read,filter,export}`, `audit.entity.history.read` |
| Tableau de bord | 4 | `dashboard.school.{read,drilldown,export,print}` |
| Élèves & inscriptions | 37 | `students.*` (identité, classe, cycle de vie, compte, annuaire), `families.*`, `enrollments.*` |
| Effectifs & dépôts | 12 | `headcounts.*`, `contributions.*` |
| Centre financier | 62 | caisse, encaissement, reçus, décisions, fonds anticipés, plans, rapports, vues VF-01 à VF-04, recouvrement |
| Paramètres | 55 | année scolaire, structure/classes/sections/options, tarifs, frais, politiques, documents, sauvegardes, diagnostic |
| Personnel | 23 | agents, affectations, fonctions, liens de compte, enfants du personnel, retenues |
| Intendance | 21 | `inventory.assets.*`, `inventory.stock.*`, `inventory.counts.*` |
| Notifications & communications | 16 | `communications.*` (dont SMS), `notifications.internal.*` |
| Documents | 6 | ouvrir, imprimer, régénérer, historique |
| Synchronisation & hors ligne | 9 | appareils, conflits, armement caisse hors ligne, quarantaine |
| Migration & import | 12 | élèves, personnel, historique financier |

La liste complète, avec risque et politique hors connexion, est dans `capability_catalog` (source de vérité en base).

---

## 4. Matrice actuelle Rôle × Domaine (nombre de capacités détenues / total du domaine)

| Rôle | Accès 11 | Audit 4 | Tableau 4 | Élèves 37 | Effectifs 12 | Finance 62 | Paramètres 55 | Personnel 23 | Intendance 21 | Comm. 16 | Docs 6 | Sync 9 | Import 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ADMIN_SYSTEME_ECOLE | **11** | 4 | **0** | **0** | 0 | 2 | **55** | 2 | 0 | 5 | 3 | 6 | 0 |
| PROMOTEUR | 0 | 4 | 4 | 18 | 11 | 38 | 12 | 9 | 10 | 4 | 3 | 0 | 2 |
| GESTIONNAIRE | 0 | 4 | 4 | 18 | 11 | 45 | 12 | 18 | 10 | 4 | 3 | 0 | 2 |
| RESPONSABLE_FINANCE | 0 | 4 | 4 | 8 | 0 | 39 | 7 | 0 | 0 | 2 | 3 | 0 | 2 |
| PREFET_ETUDES | 0 | 1 | 4 | 26 | 8 | 26 | 5 | 8 | 0 | 10 | 3 | 0 | 2 |
| DIRECTION_SECTION | 0 | 1 | 4 | 26 | 8 | 26 | 5 | 8 | 0 | 10 | 3 | 0 | 2 |
| DIRECTEUR_ETUDES | 0 | 1 | 4 | 14 | 8 | 0 | 3 | 0 | 0 | 9 | 3 | 0 | 0 |
| DIRECTEUR_DISCIPLINE | 0 | 1 | 4 | 12 | 5 | 0 | 3 | 0 | 0 | 10 | 3 | 0 | 0 |
| CAISSIER | 0 | 0 | 1 | 34 | 4 | 43 | 7 | 0 | 0 | 2 | 4 | 4 | 2 |
| SECRETARIAT | 0 | 0 | 0 | 10 | 5 | 0 | 4 | 3 | 0 | 6 | 4 | 0 | 0 |
| INTENDANT | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 1 | 21 | 2 | 3 | 0 | 0 |

### Ce que chaque rôle voit réellement (menu et tableau de bord calculés aujourd'hui)

| Rôle | Menus ouverts (règle client par préfixe) | « Modèle » de tableau de bord deviné | Widgets alimentés |
|---|---|---|---|
| ADMIN_SYSTEME_ECOLE | Paramètres, Personnel, **Centre financier**, Documents, Sync, Communication, Accès | **GENERAL** | **aucun** → panneau « Évolution du recouvrement » vide + « Données de recouvrement non disponibles », bouton « Rechercher un élève » sans droit élèves |
| PROMOTEUR / GESTIONNAIRE | 9 modules | GOVERNANCE | effectifs, mouvements, recouvrement, frais |
| RESPONSABLE_FINANCE | Paramètres, Élèves, Finance, Documents, Accès | FINANCE | recouvrement, frais |
| PREFET / DIRECTION_SECTION | 7 modules | SCHOOL_DIRECTION | effectifs, mouvements, recouvrement, frais |
| DIRECTEUR_ETUDES / DISCIPLINE | 5 modules | SCHOOL_DIRECTION | effectifs, mouvements |
| CAISSIER | Paramètres, Élèves, Finance, Documents, Sync | CASHIER | caisse du jour, recouvrement |
| SECRETARIAT | 6 modules | SECRETARIAT (titre « Administration scolaire ») | effectifs |
| INTENDANT | Paramètres, Personnel, Documents, Intendance | INTENDANCE | **aucun** → panneau recouvrement vide + « Aucune donnée d'intendance », bouton « Rechercher un élève » sans droit élèves |

**Backend** : toutes les mutations testées passent par `require(cap)` ; la portée SECTION/CLASS est vérifiée dans
schooling, personnel, effectifs, recouvrement, documents, communications. **Frontend** : menus et tableau de bord
déduits côté client ; boutons majoritairement conditionnés par `permissions.includes(cap)` (173 capacités école
référencées dans le frontend).

---

## 5. Défauts architecturaux

### 5.1 Personnalisation par école
1. **Le clonage fige les rôles.** Pour adapter « Préfet » dans l'école A, on crée `CUSTOM_xxxx` (copie). Quand la
   plateforme ajoute une capacité au Préfet standard (ce qui est arrivé : +9 capacités depuis le contrat), **les clones ne
   la reçoivent jamais**. Le rôle perd aussi son identité métier : le dashboard, les statistiques et le support ne
   savent plus que `CUSTOM_C022D0A045` est un Préfet.
2. **Pas de notion « obligatoire / ajustable / interdit »** par capacité et par rôle. Seule protection : « il reste au
   moins un détenteur de `access.roles.manage` ».
3. **Pas de garde-fous de séparation des tâches** déclarés (ex. encaisser et annuler en autorité supérieure sur un même
   rôle) : aujourd'hui seule la décision manuelle du propriétaire les évite.

### 5.2 Catalogue
4. **Écart contrat ↔ base.** `CAPABILITY_REGISTRY.json` : 282 ; base : 288 (6 absentes du contrat :
   `migration.finance_history.{analyze,execute}`, `migration.staff.{analyze,execute}`, `platform.access.manage`,
   `platform.collaborators.manage`). `POINT3B_ROLE_DECISIONS_FINAL.json` diffère de la base pour **10 rôles sur 12**
   (ex. CAISSIER +9, GESTIONNAIRE +13, DIRECTEUR_ETUDES −8 personnel / +5 élèves). Les tests vérifient le JSON, pas la base.
5. **70 capacités école sans aucun contrôle backend trouvé** (recherche littérale). Trois cas :
   fonctionnalités pas encore construites (`settings.backups.*`, `settings.diagnostics.*`, `sync.finance.*`, vues VF) ;
   capacités vérifiées sous un autre nom (`enrollments.read` → `students.read`) ; capacités d'interface
   (`dashboard.school.read`, `settings.work_year.select`) jamais utilisées. Une capacité affichée dans l'écran des rôles
   mais qui ne protège rien **trompe l'administrateur**.
6. **Doublons** : `finance.products.manage` / `settings.products.manage` ; `documents.history.read` /
   `settings.documents.history.read` ; `contributions.read` / `contributions.register.read` ;
   `headcounts.by_{class,section,option}.read` en plus de `headcounts.read`.
7. **Granularité d'export incohérente** : ~40 capacités `*.export_pdf` / `*.export_xlsx` / `*.print` pour les mêmes
   données. Le format ne change pas le risque (les mêmes données sortent) ; seules quelques exportations sensibles
   (journal de caisse, audit, VF-01) justifient une capacité propre.
8. **Incohérences de métadonnées** : `finance.payments.reverse` (CRITICAL) a la politique `READ_CACHE` ; plusieurs
   `*.manage` sont `READ_CACHE` alors qu'elles écrivent.
9. **Portée `CYCLE`** existe dans l'enum mais n'est ni proposée par l'API ni utilisée. `CLASS` est proposée mais 0
   affectation l'utilise. Base réelle : SCHOOL 1516, SECTION 41.

### 5.3 Règles codées sur un nom de rôle
10. Backend : `ADMIN_SYSTEME_ECOLE` (indicateur « école sans administrateur » dans l'annuaire plateforme) et
    `MANAGER_SYSTEME` (destinataires d'alertes, premier manager). Acceptable pour le **provisionnement**, mais
    l'indicateur devrait reposer sur « détient le socle administrateur », pas sur le code.
11. Frontend : aucun test direct de code de rôle, **mais** `home.tsx` reconstruit un « rôle » à partir de combinaisons
    de capacités (`modelOf`). C'est un test de rôle déguisé : fragile dès qu'une école ajuste un rôle (un Préfet sans
    `headcounts.movements.read` tombe en « SECRETARIAT »).

### 5.4 Interface École
12. **Menu calculé côté client** par préfixe : une seule capacité `finance.anticipation_plans.read` ouvre tout le
    « Centre financier » à l'Administrateur. La Plateforme, elle, reçoit son menu **calculé par le serveur**
    (`/platform/team/me`).
13. **Tableau de bord** : widgets sans déclaration de capacités requises ; titres et panneaux affichés même vides ;
    l'Administrateur et l'Intendant voient un panneau financier vide ; bouton « Rechercher un élève » sans droit.
14. **Shell** : la Plateforme utilise `accountDock` (compte en bas de la barre latérale), fil d'Ariane commun,
    titres normalisés. L'École garde le compte en haut à droite et n'utilise pas le fil d'Ariane.
15. **Erreurs** : une seule `ErrorBoundary`, à la racine (`main.tsx`). Le moindre plantage d'un composant remplace
    **tout l'écran** (shell compris) par « EduSync reste disponible… Recharger la page ». Pas de distinction réseau /
    session / permission / introuvable / serveur au niveau de l'écran.

---

## 6. Benchmark externe — ce qu'on retient

| Référence | Concept | Pour EduSync |
|---|---|---|
| **GitHub** (rôles de dépôt personnalisés) | Un rôle personnalisé part d'un **rôle de base** et **ajoute** des permissions | Retenu : rôle standard = base, l'école ajuste par différence |
| **Salesforce** (profils minimaux + permission sets, « muting ») | Tout est additif ; un groupe peut **retirer** une permission via un jeu de « muting », à utiliser avec parcimonie | Retenu : retrait possible **dans le contexte d'un rôle**, jamais un « deny » global caché |
| **Google Cloud IAM** | Rôles prédéfinis maintenus par l'éditeur et **mis à jour automatiquement** ; rôles personnalisés limités à leur organisation ; politiques de refus séparées | Retenu : la plateforme maintient les rôles standards, les écoles en héritent ; refus = garde-fous plateforme explicites |
| **Azure RBAC** | Portées imbriquées (groupe → abonnement → ressource), héritage vers le bas ; assigner au niveau le plus haut suffisant | Retenu : portées SCHOOL ⊃ SECTION ⊃ CLASS, héritage descendant |
| **Auth0 Organizations** | Rôles par organisation ; un utilisateur a des rôles différents dans chaque organisation ; permissions = union | Déjà en place (appartenance par école, union) |
| **Keycloak** | Rôles composites, groupes ; administration fine séparée des rôles applicatifs | Retenu : séparer « qui administre les accès » (gouvernance) des capacités métier — déjà fait par l'anti-escalade |

Non retenu : politiques ABAC génériques (langage de règles) — complexité disproportionnée pour des écoles ;
« deny » global par utilisateur — rend les droits illisibles pour un administrateur d'école.

---

## 7. Architecture cible recommandée

### 7.1 Principe
`droits effectifs(utilisateur, école) = ⋃ sur ses affectations actives [ base(rôle) + ajouts(école, rôle) − retraits(école, rôle) ] ∩ portée(affectation)  ∪  exceptions temporaires`

- **Rôle standard** : défini et maintenu par la plateforme (comme aujourd'hui), jamais copié.
- **Politique d'école** : une table de **différences** par (école, rôle standard) : `GRANT` ou `REVOKE` d'une capacité,
  avec motif, auteur, date, version. Une évolution plateforme du rôle standard arrive **automatiquement** dans toutes
  les écoles, sauf là où l'école a explicitement retiré la capacité.
- **Rôles propres à l'école** : conservés pour les profils réellement nouveaux (ex. « Assistant promoteur »),
  avec un champ `base_role_id` (parenté affichée, statistiques, dashboard par famille).
- **Le moteur calcule, l'interface consomme** : un endpoint `/access/me` (équivalent de `/platform/team/me`) renvoie
  capacités effectives (avec portées), menu, widgets autorisés. Le frontend ne déduit plus rien.

### 7.2 Métadonnées ajoutées au catalogue

| Champ | Valeurs | Rôle |
|---|---|---|
| `school_adjustable` | `true` / `false` | `false` = jamais ajoutée ni retirée par une école (ex. `platform.*`, `access.grants.exception` si décidé) |
| Par rôle standard : `locked` | liste | Capacités que l'école **ne peut pas retirer** de ce rôle (socle) |
| Par rôle standard : `ceiling` | liste ou « tout le catalogue ajustable » | Capacités que l'école **peut ajouter** à ce rôle |
| `sod_conflicts` | paires | Séparation des tâches : refus si une même personne cumule les deux (valeurs = **décision propriétaire**) |

### 7.3 Administrateur école — socle protégé (proposition à valider)

| Catégorie | Capacités |
|---|---|
| **Obligatoires (verrouillées)** | `access.users.{read,create,update,activate,credentials.reset}`, `access.roles.{read,manage}`, `access.permissions.assign`, `access.scopes.assign`, `audit.school.read`, `settings.school_identity.read`, `settings.academic_year.read`, `settings.structure.read`, `notifications.internal.read` |
| **Ajustables** | paramètres de structure, année, tarifs, documents, sauvegardes, appareils, communications internes, plans anticipés |
| **Interdites par défaut** (aucune exécution métier implicite — décision 0008) | encaissement, caisse, annulations, décisions financières, cycle de vie élève, inventaire |
| **Réservées plateforme** | `platform.*`, création/réinitialisation de l'administrateur initial (`platform.school_admin.bootstrap`), suspension d'école, portefeuille SMS |

Invariants serveur : au moins **un** membre actif détenant le socle complet (pas seulement `access.roles.manage`) ;
un administrateur ne retire jamais le socle de son propre rôle ; seule la plateforme peut restaurer un socle perdu.

### 7.4 Portées

| Portée | Garder ? | Justification |
|---|---|---|
| SCHOOL | Oui | Défaut |
| SECTION | Oui | Préfet / Directeur de section (déjà 41 affectations) |
| CLASS | Oui, réservée | Futur Enseignant / titulaire ; déjà supportée par l'API et `scope_allows` |
| CYCLE | **Retirer de l'enum** tant qu'aucun cas métier | Inutilisée, non proposée |
| OWN | **Pas une portée** : condition métier dans le domaine | « Sa propre caisse », « ses propres paiements » sont déjà vérifiés par le code métier ; en faire une portée générique complexifie sans gain |

### 7.5 Modifications du catalogue (proposées — chaque ligne à valider)

**À conserver** : l'essentiel (≈ 200) — accès, audit, élèves, finance opérationnelle, paramètres, personnel, intendance.

**À ajouter** (seulement si le métier le demande) :
- Domaine **Académique** (aucune capacité aujourd'hui) — *BUSINESS_DECISION_REQUIRED* : périmètre exact (évaluations,
  notes, bulletins, emploi du temps) et rôle Enseignant. Gabarit proposé : `academic.read`, `academic.assessments.manage`,
  `academic.grades.enter` (portée CLASS), `academic.results.validate` (SECTION), `academic.bulletins.publish`.
- `access.me.read` n'est pas nécessaire (toujours autorisé pour soi).

**À fusionner / supprimer** :
- `finance.products.manage` → `settings.products.manage` (même action) ; `settings.documents.history.read` →
  `documents.history.read` ; `contributions.register.read` → `contributions.read`.
- `headcounts.by_{class,section,option}.read` → `headcounts.read` (la portée filtre déjà).
- Paires `*.export_pdf` / `*.export_xlsx` / `*.print` d'une même vue → `<vue>.export` (garder séparées : journal de
  caisse, audit, VF-01).
- `settings.work_year.select` → supprimer (choisir l'année consultée n'est pas un droit).
- `dashboard.school.{drilldown,export,print}` → supprimer ; le tableau de bord se construit à partir des capacités
  métier (§8). `dashboard.school.read` → supprimer (tout membre a un accueil).
- Capacités de fonctionnalités inexistantes (`settings.backups.*`, `settings.diagnostics.*`, `sync.finance.*` non
  contrôlées, VF non branchées) → marquer `status=PLANNED` et **masquer** dans l'écran des rôles tant qu'elles ne
  protègent rien.
- Corriger les politiques hors connexion incohérentes (`finance.payments.reverse` → `SERVER_ONLY`).

---

## 8. Tableau de bord adaptatif

Chaque widget est déclaré une seule fois côté serveur :

```
{ id, titre, requires: [capacités, toutes], any_of: [au moins une], portée: SCHOOL|SECTION, priorité, action: module }
```

Le serveur renvoie la liste des widgets autorisés **avec leurs données** (ou leur endpoint) ; le frontend les affiche
dans l'ordre de priorité. Un widget sans données affiche un état utile (« Aucune caisse ouverte aujourd'hui —
Ouvrir ma caisse »), jamais un panneau vide d'un autre métier.

| Widget | Requiert | Pour qui (par défaut) |
|---|---|---|
| Comptes à activer / invitations en attente | `access.users.read` | Administrateur |
| Rôles et affectations à revoir (sans portée, expirant) | `access.roles.read` | Administrateur |
| Année scolaire : état, prochaine étape | `settings.academic_year.read` | Administrateur, direction |
| Paramétrage incomplet (readiness existant `settings/overview`) | `settings.school_identity.read` | Administrateur |
| Structure : sections / classes actives | `settings.structure.read` | Administrateur |
| Dernières actions administratives | `audit.school.read` | Administrateur, gouvernance |
| Appareils et synchronisation | `sync.status.read` | Administrateur |
| Ma caisse du jour | `finance.cash.read` + `finance.cash.open` | Caissier |
| Encaisser rapidement | `finance.checkout.collect` | Caissier |
| Effectifs | `headcounts.read` | Direction, secrétariat |
| Mouvements récents | `headcounts.movements.read` | Direction |
| Évolution du recouvrement | `finance.recovery.monthly.read` | Gouvernance, finance, chef de section |
| Situation par familles de frais | `finance.analysis.by_fee.read` | Gouvernance, finance |
| Stocks faibles / inventaires en cours | `inventory.stock.low_alerts.read` / `inventory.counts.read` | Intendant |
| Rechercher un élève | `students.read` | Tous ceux qui ont le droit |

Le titre (« Poste de caisse », « Administration de l'école »…) vient du **libellé du rôle** (ou du rôle de base d'un
rôle propre), pas d'une devinette sur les capacités.

---

## 9. Shell École homogène et erreurs

| Élément | Cible (référence Plateforme) |
|---|---|
| Compte | `accountDock` : bloc compte en bas de la barre latérale (bureau) et du menu téléphone |
| Changer d'espace | Même entrée de menu compte |
| Fil d'Ariane | Composant commun `navigation.tsx` pour les fiches profondes |
| Menu | Fourni par `/access/me` (serveur), comme `/platform/team/me` |
| Hors connexion | Déjà commun (bandeau, politique 7 jours) |

Erreurs — une `ScreenBoundary` **par module** (le shell reste affiché) + un type d'erreur normalisé :

| Cas | Message | Action |
|---|---|---|
| Réseau | « Connexion impossible » + cache si disponible | Réessayer |
| Données en cache | Affichage + date de la donnée | Réessayer en ligne |
| Session expirée (401) | Renouvellement silencieux, sinon connexion | — |
| Permission (403) | « Vous n'avez pas accès à cette page » + qui contacter | Retour accueil |
| Introuvable (404) | « Élément introuvable ou supprimé » | Retour liste |
| Serveur (5xx) | « Service momentanément indisponible » | Réessayer |
| Plantage d'affichage | « Cette partie n'a pas pu s'afficher » dans la zone du module | Réessayer (remonte le module) |

---

## 10. Plan de migration (sans casser les données)

1. **Réaligner les contrats sur la base** : régénérer `CAPABILITY_REGISTRY.json` et les décisions de rôles depuis la
   base réelle (ou l'inverse, selon ce que le propriétaire valide) ; ajouter un test qui compare base ↔ contrat.
2. **Migration additive** : table `rbac_school_role_policies(school_id, role_id, capability_code, effect, reason,
   created_by, created_at, version)` avec RLS école ; colonnes catalogue `school_adjustable`, `status` ;
   table `rbac_role_constraints(role_id, capability_code, kind LOCKED|CEILING)`.
3. **Moteur** : `effective_capability_grants` et `memberships.permissions` intègrent GRANT/REVOKE ; aucune
   donnée existante ne change → droits identiques avant/après (test de non-régression sur toutes les affectations).
4. **Rôles clonés existants** : on ne les convertit pas de force. Un assistant propose, pour un `SCHOOL_CUSTOM` clone
   d'un standard, de le remplacer par « standard + différences » (calculées automatiquement), après validation de
   l'école ; les affectations sont reportées dans la même transaction, auditées.
5. **Fusions de capacités** : alias temporaires (l'ancienne capacité continue d'ouvrir le même cas d'usage) pendant
   une version, puis suppression ; les rôles sont mis à jour par migration.
6. **API `/access/me`** puis bascule du frontend (menu, tableau de bord, boutons) ; suppression de `modelOf` et des
   préfixes.
7. **Shell** : `accountDock`, fil d'Ariane, `ScreenBoundary` par module.

Chaque étape est déployable seule ; aucune ne supprime de donnée.

---

## 11. Stratégie de tests

- **Moteur** : tests unitaires des formules (base + ajouts − retraits, union de deux rôles dont un a retiré la
  capacité, portée SECTION vs SCHOOL, exception temporaire, rôle archivé).
- **Invariants** : socle administrateur non retirable ; dernier administrateur ; anti-escalade ; séparation des tâches.
- **Non-régression** : snapshot des droits effectifs de **toutes** les affectations avant/après migration (doit être
  identique).
- **Contrat** : base ↔ `CAPABILITY_REGISTRY.json` ; chaque capacité `ACTIVE` est contrôlée par au moins un endpoint
  (test qui échoue pour les capacités « fantômes ») ; chaque endpoint de mutation contrôle une capacité.
- **Interface** : pour chaque rôle standard, Playwright vérifie menus, widgets et absence de boutons interdits ;
  pour un rôle ajusté (ex. Préfet sans finance), les widgets financiers disparaissent.
- **Backend autorité** : pour chaque bouton masqué, l'appel direct à l'API renvoie 403.
- **Erreurs** : chaque type (réseau, 401, 403, 404, 5xx, plantage) garde le shell et propose l'action prévue.

---

## 12. Estimation des fichiers / modules impactés

| Zone | Fichiers | Charge |
|---|---|---|
| Migrations | 1 à 2 nouvelles (politiques école, contraintes de rôle, métadonnées catalogue, fusions) | Moyenne |
| Moteur | `adapters/postgres_authorization.py`, `adapters/postgres_repositories.py` (`permissions`), `iam/domain/authorization.py` | Moyenne |
| API accès | `modules/access/api/router.py` (politiques, socle, `/access/me`, assistant de conversion) | Forte |
| Contrats | `contracts/CAPABILITY_REGISTRY.json`, `POINT3B_ROLE_DECISIONS_FINAL.json` + tests | Faible |
| Routeurs métier | uniquement pour les capacités fusionnées (alias) | Faible |
| Frontend | `App.tsx` (menu, shell École), `home.tsx` (réécrit), `access.tsx` (écran politique par rôle), `platform/shell.tsx`, nouveau `ScreenBoundary` | Forte |
| Tests | backend RBAC, contrats, Playwright par rôle | Forte |

---

## Décisions demandées au propriétaire avant implémentation

1. Valider le modèle « rôle standard + différences par école » (au lieu du clonage).
2. Valider le socle obligatoire de l'Administrateur école (§7.3).
3. Choisir pour chaque fusion de capacités (§7.5) : fusionner ou garder.
4. Domaine Académique et rôle Enseignant : périmètre et calendrier.
5. Paires de séparation des tâches à imposer (le cas échéant).
6. Source de vérité en cas d'écart contrat ↔ base (§5.2-4).

---

## Mise en œuvre — passe RBAC (décisions propriétaire du 23/10/2026)

| Décision | Réalisation | Preuve |
|---|---|---|
| 1. Standard + GRANT − REVOKE | `rbac_school_role_policies` (0085), moteur `adapters/rbac_effective.py` (une seule définition SQL pour la connexion, les portées et `/access/me`), API `GET/PUT /access/roles/{id}/policy`, écran « Ajuster pour l’école » | sonde `tools/local/rbac_policy_probe.py` (REVOKE → 403 backend, GRANT → menu) |
| 2. Socle protégé Administrateur | `rbac_role_constraints` LOCKED (14 capacités d’administration/configuration, aucune opération métier), trigger SQL | test registre + refus base dans la sonde |
| 3. Fusion des exports | 10 capacités `*.export`, 23 variantes `ALIAS` équivalentes (expansion dans le moteur, dans les deux sens) ; verbes métier jamais fusionnés | snapshot : 0 droit perdu ; 43 membres obtiennent les autres formats d’un export qu’ils avaient déjà |
| 4. Académique non construit ; capacités non implémentées cachées | `lifecycle` PLANNED/DEPRECATED/ALIAS cachés de l’éditeur, jamais attribuables (trigger) | tests registre |
| 5. Séparation des tâches | `rbac_sod_rules` + surcharges école : SELF_ELEVATION BLOCK (fixe), GOVERNANCE_GRANT REQUIRE_APPROVAL, 3 paires financières WARN ; demandes `rbac_change_requests` (CHECK SQL : jamais auto-approuvées) | sonde (auto-approbation refusée par l’API et par la base) |
| 6. Registre canonique | `contracts/CAPABILITY_REGISTRY.json` 2.0.0 (298 capacités, rôles standards, socle, règles) ; `tools/ci/rbac_registry.py check` ; job CI `rbac-contract` | 0 dérive |
| 7. 70 capacités sans contrôle | 0 ACTIVE ; 43 PLANNED, 20 DEPRECATED, reste ALIAS ; test : toute capacité ACTIVE est contrôlée par le backend | `test_rbac_canonical_registry.py` |
| 8. `/access/me` | projection serveur : permissions, portées, rôles, navigation, widgets, raccourcis ; plus de préfixes ni `modelOf` | tests projection par rôle standard |
| 9. Tableau de bord par capacités | `home.tsx` réécrit : cartes déclarées par le serveur ; l’Administrateur n’a plus ni recouvrement ni « Rechercher un élève » | Vitest + Playwright |
| 10. Shell aligné | compte dans la barre latérale (`accountDock`), fil d’Ariane, mêmes conventions mobile | Playwright bureau + mobile |
| 11. Boundaries locales | `ScreenBoundary` par écran (École et Plateforme), erreurs classées (réseau, hors ligne, session, permission, introuvable, serveur) | Playwright : écran en panne, navigation conservée |
| 12. Additive, réversible, identique | 0085 sans suppression ; `migrations/rollback/0085_school_rbac_policies.down.sql` ; snapshot avant/après | base locale réelle : 971 affectations, 0 différence ; CI : base vierge jusqu’à 0084 + jeu de rôles, 0 différence |

Conversion des rôles clonés : jamais automatique. `GET /access/roles/{id}/conversion-preview` simule chaque membre concerné ;
`POST …/convert` refuse si un seul droit effectif change, et revérifie tous les membres dans la même transaction.
