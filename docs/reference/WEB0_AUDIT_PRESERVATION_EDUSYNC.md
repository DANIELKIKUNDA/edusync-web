# WEB-0 — Audit de préservation EduSync

**Date : 2026-09-11**  
**Source auditée :** archive fournie `b427a52c-cb13-4a39-87c5-90efadf15f24.zip`  
**SHA-256 de l’archive auditée :** `50e618c388346c7ebb671c12e6080fafb77d262c8daa2ba9cde05bfd97f18b71`  
**Mode :** audit statique de préservation, sans modification du code métier ni des bases.

## 1. Verdict exécutif

**VERDICT WEB-0 : PRÊT POUR UNE MIGRATION PRÉSERVATION-FIRST VERS UN SAAS MULTI-ÉCOLE.**

EduSync ne doit pas être réécrit comme un nouveau produit. L’archive contient déjà un produit métier très avancé, dont de nombreux domaines disposent de preuves de certification, de tests, d’exports documentaires et de scénarios Windows. La migration Web doit considérer ces éléments comme des **contrats de référence**.

La bonne stratégie n’est pas « convertir PySide6 en Web », mais :

1. geler les comportements métier certifiés ;
2. extraire progressivement les cas d’usage hors de `SchoolDatabase` ;
3. construire un monolithe modulaire DDD/Clean/Hexagonal sur FastAPI/PostgreSQL ;
4. reconstruire l’interface React/PWA à parité fonctionnelle ;
5. ajouter le multi-école, l’Atelier Pro, RBAC, audit SaaS, cache, notifications et synchronisation offline-first autour de ce métier existant ;
6. prouver la parité module par module avant de retirer le Desktop comme référence.

Le Desktop actuel doit rester intact pendant la construction de la nouvelle génération.

## 2. État technique observé dans l’archive

### 2.1 Socle actuel

- Application : Python + PySide6 + SQLite.
- Version déclarée dans `app/__init__.py` : `0.11.0-rc.1`.
- `app/db/migrations.py` déclare `LATEST_SCHEMA_VERSION = 17`.
- `app/db/schema.sql` contient **71 tables**.
- L’archive contient **30 fichiers de tests** et **219 fonctions de test** détectées statiquement.
- `python -m compileall -q app tests` : **PASS** dans l’environnement d’audit.
- L’interface appelle directement `self.db.*` à **324 endroits**, couvrant **173 méthodes distinctes**. C’est la principale dette architecturale à traiter avant le Web.

### 2.2 Incohérence documentaire à corriger

Le `README.md` et `CHECKPOINT.md` parlent encore d’un schéma v14 alors que les migrations actuelles vont jusqu’à v17. Cette incohérence est documentaire ; elle ne justifie aucune régression du schéma actuel.

**Décision WEB-0 :** la source de vérité de version de schéma est le code de migration actuel. Toute documentation Web nouvelle doit être générée/contrôlée depuis une constante ou métadonnée unique afin d’éviter ce décalage.

## 3. Actifs produit à préserver

### 3.1 Paramètres

Le produit contient déjà un centre de configuration riche : identité de l’école, années scolaires, sections/options, classes pédagogiques annuelles, frais, tarifs, politiques d’inscription, avantages, encaissement, plans anticipés, contributions, articles, documents, sauvegardes, utilisateurs et personnel.

**Préservation : TRÈS FORTE.**

Le Web doit préserver les portées existantes : permanent / établissement / annuel / historique. Le multi-école ajoute un `school_id` sans changer la sémantique métier interne d’une école.

### 3.2 Élèves, inscriptions, familles

Les artefacts du projet documentent des parcours Windows validés : nouvelle inscription, foyer existant, plusieurs enfants, famille mixte, famille nombreuse, enfant d’agent, réinscription, ancien élève, historique, encaissement, recherche transversale et familles éligibles.

**Préservation : TRÈS FORTE.**

À conserver notamment :

- identité élève permanente ;
- inscription annuelle ;
- `family_id` permanent ;
- résolution assistée du foyer sans fusion silencieuse ;
- famille nombreuse avec bénéficiaire explicite ;
- lien enfant-personnel explicite ;
- historique de statut ;
- recherche transversale ;
- pagination et listes administratives ;
- exports filtrés.

### 3.3 Effectifs & dépôts

Le domaine dispose déjà d’agrégations par classe/section/filière, mouvements, registres de dépôts, filtres, PDF/Excel et recette Windows.

**Préservation : FORTE.**

Le Web peut réimplémenter les read models en PostgreSQL mais doit conserver les mêmes définitions d’« actif », mouvements, F/G/T, périmètres et totaux.

### 3.4 Personnel

Le modèle sépare identité de l’agent, fonction, affectations, périmètre et historique. La sortie d’un agent conserve l’historique et peut désactiver l’accès lié.

**Préservation : FORTE.**

Le nouveau rôle `INTENDANT` ne doit pas être codé comme un simple `if role == ...`; il doit devenir un modèle de permissions configurable.

### 3.5 Utilisateurs et accès

L’existant ne connaît que quatre rôles techniques : `ADMIN`, `SECRETARIAT`, `CAISSIER`, `DIRECTION`. Les contrôles sont dispersés via `require_roles()` et des conditions UI.

**Préservation métier : MOYENNE. Implémentation : À REMPLACER.**

À conserver : liaison éventuelle compte ↔ personnel, activation/désactivation, traçabilité, notion de profils métier.  
À remplacer : autorisations codées en dur par un RBAC multi-école à permissions.

### 3.6 Finance

Le noyau financier possède une forte densité de règles : charges nettes, allocations, reçus, caisse, remboursements/annulations, fonds anticipés, décisions financières, responsabilités, retenues hors caisse, paiements familiaux, multi-devise, historique d’année et lifecycle élève.

Les artefacts de l’archive contiennent une recette finance finale avec **29 scénarios documentés, 29 exécutés, 29 PASS, 0 FAIL, 0 skipped**, ainsi qu’une certification UI/UX du Centre financier et une certification des outils spécialisés.

**Préservation : MAXIMALE.**

Règles à figer comme invariants :

- CDF/FC et USD ne sont jamais additionnés ni convertis implicitement ;
- un paiement est distinct d’une prise en charge, d’une retenue salariale et d’un fonds anticipé ;
- `payment_allocations` reste la vérité de ventilation ;
- une exonération nette à zéro ne produit pas de faux paiement ;
- abandon/transfert ne remboursent pas automatiquement ;
- ancienne dette = charge historique, paiement réel aujourd’hui ;
- échec PDF après commit ne doit jamais annuler ni doubler le paiement ;
- double validation doit être idempotente ;
- plan anticipé et fonds anticipé restent deux produits comptables distincts.

### 3.7 Documents et exports

L’inventaire canonique du projet contient **16 générateurs PDF/Excel** : registres financiers, synthèses, reçus, lots familiaux, fonds anticipés, relevé élève, rapports journaliers/périodiques, effectifs, registre officiel, contributions, journal de caisse et modèle d’import.

**Préservation : MAXIMALE.**

Ces documents deviennent des **golden masters**. Le passage Web ne doit ni appauvrir les colonnes, ni supprimer les totaux, ni dégrader les logos, filtres, pagination ou formats.

Décision : conserver les générateurs Python server-side lorsque possible derrière un `DocumentGeneratorPort`, plutôt que les réécrire immédiatement en JavaScript.

### 3.8 Imports

L’import historique est plus adapté à une industrialisation qu’à un gel strict.

**Préservation des données : MAXIMALE. UX/Workflow : ENRICHISSABLE.**

Le Web pourra ajouter : staging, mapping de colonnes, preview, validation, détection de doublons, reprise, idempotence, journal d’import et rapports de rejet.

### 3.9 Sauvegarde/restauration

Le mécanisme SQLite actuel est très pertinent comme référence de continuité locale, mais le SaaS nécessitera une stratégie différente : sauvegardes PostgreSQL, stockage objet, restauration testée, PITR si retenu, rétention et copie hors VPS.

**Préservation de la doctrine : FORTE. Implémentation : À REMPLACER.**

## 4. Audit actuel : ce qui existe et ce qui manque pour un SaaS

### 4.1 Audit actuel

La table `audit_log` contient actuellement :

- `id`
- `occurred_at`
- `user_id`
- `action`
- `entity_type`
- `entity_id`
- `old_json`
- `new_json`
- `reason`

Le mécanisme est utilisé dans de nombreux cas d’usage et doit être conservé comme doctrine.

### 4.2 Limites SaaS

Il manque notamment :

- `school_id` ;
- identité de membership/tenant ;
- rôle/permissions au moment de l’action ;
- source (`WEB`, `OFFLINE`, `SYNC`, `SYSTEM`, `IMPORT`) ;
- `device_id` ;
- `request_id` / `correlation_id` ;
- `causation_id` ;
- `idempotency_key` ;
- résultat (`SUCCESS`, `REJECTED`, `FAILED`) ;
- métadonnées de synchronisation ;
- protection explicite append-only.

### 4.3 Doctrine d’industrialisation Audit

Créer un sous-système transversal `Audit` avec deux niveaux :

1. **Audit plateforme** : création/suspension d’école, changements de plan, administrateurs, feature flags, opérations support.
2. **Audit école** : inscriptions, paiements, caisse, utilisateurs, paramètres, personnel, intendance, documents, imports.

Pour toute mutation critique, l’événement d’audit doit être écrit **dans la même transaction PostgreSQL** que l’opération métier, ou via une transaction/outbox garantissant l’atomicité.

L’utilisateur applicatif ne doit pas pouvoir mettre à jour/supprimer une ligne d’audit. Les corrections créent de nouveaux événements.

## 5. Analyse de la dette architecturale

### 5.1 `SchoolDatabase` est aujourd’hui un façade/god-object

`SchoolDatabase` compose de nombreux mixins et expose directement la connexion SQLite. L’UI dépend de cette façade à 173 méthodes distinctes.

**Conséquence :** tenter de remplacer SQLite par PostgreSQL directement dans cette classe créerait un portage fragile et très coûteux.

### 5.2 Plan d’extraction sans régression

Ne pas réécrire les règles métier. Extraire progressivement :

- `domain` : entités, value objects, invariants purs ;
- `application` : use cases ;
- `ports` : repositories, unit of work, audit, documents, notifications, cache ;
- `adapters` : PostgreSQL, Redis, S3, API, Web, local store ;
- `legacy_adapter` : accès temporaire aux règles Desktop pendant la transition si nécessaire.

Chaque extraction doit être accompagnée d’un test de parité avec une fixture Desktop.

## 6. Stratégie de préservation par Golden Masters

Créer un répertoire de référence versionné :

`preservation/golden/`

Il contiendra :

- base DEMO assainie/sanitisée ;
- snapshots JSON de cas d’usage ;
- PDF de référence ;
- Excel de référence ;
- totaux par année/devise ;
- scénarios d’inscription ;
- scénarios financiers ;
- reçus ;
- registres effectifs ;
- journal de caisse ;
- rapports et vues financières.

Un module Web n’est certifié que si :

1. ses données PostgreSQL correspondent à la fixture migrée ;
2. les invariants métier correspondent ;
3. les exports correspondent sémantiquement ;
4. les permissions et l’audit sont corrects ;
5. l’isolation multi-école est prouvée ;
6. les scénarios offline applicables sont prouvés.

## 7. Multi-école : règle de préservation

Le produit cible est multi-école, mais **pas multi-organisation**. La grande plateforme organisationnelle reste séparée.

Chaque agrégat métier doit être rattaché à une école. L’ajout de `school_id` ne doit pas changer les identifiants métier historiques, matricules, numéros de reçus ou règles annuelles sans décision explicite.

Les séquences doivent devenir au minimum uniques par école, par exemple :

- `(school_id, receipt_no)` ;
- `(school_id, matricule)` si le matricule n’est pas global plateforme ;
- `(school_id, family_code)` ;
- `(school_id, academic_year_label)`.

## 8. Risques de migration

| Risque | Niveau | Mesure WEB-0 |
|---|---:|---|
| Réécriture métier involontaire | Critique | Golden masters + parité obligatoire |
| Fuite inter-école | Critique | `school_id` + RLS + tests d’isolation |
| Double paiement offline/sync | Critique | idempotency + inbox/outbox + protocole finance dédié |
| Perte de richesse PDF/Excel | Haute | conserver générateurs Python + golden outputs |
| RBAC trop permissif | Haute | permissions atomiques + deny-by-default |
| Audit incomplet offline | Haute | événement local + corrélation sync + audit serveur |
| Conversion REAL SQLite → numérique | Haute | PostgreSQL `NUMERIC`, réconciliation par devise |
| Numéros de reçus en collision | Critique | séquences tenant/device maîtrisées |
| Documentation obsolète | Moyenne | source de version unique + ADR |
| Migration trop large en une étape | Haute | strangler/pilotage module par module |

## 9. Décisions WEB-0

1. **Préserver le Desktop** comme référence jusqu’à certification Web de chaque domaine.
2. **Monolithe modulaire**, pas microservices, pour le premier VPS.
3. **FastAPI + PostgreSQL + React/PWA** comme cible.
4. **Redis** pour cache/coordination, jamais comme source de vérité financière.
5. **S3-compatible** derrière un port de stockage pour documents.
6. **Multi-école sans niveau Organisation**.
7. **Atelier Pro** séparé des données métier d’école.
8. **RBAC permission-based** au lieu de quatre rôles codés en dur.
9. **Audit append-only** industrialisé.
10. **Offline-first par politiques de domaine**, pas par synchronisation générique naïve.
11. **Exports existants gelés comme actifs produit**.
12. **Imports enrichissables**.
13. **Finance = domaine à préservation maximale**.

## 10. Gate de sortie WEB-0 Audit

WEB-0 Audit est considéré acquis lorsque :

- la matrice de préservation est approuvée ;
- l’architecture fondatrice est approuvée ;
- aucun code métier Desktop n’a été modifié ;
- le modèle de tenant est fixé ;
- le modèle RBAC est fixé ;
- le modèle d’audit est fixé ;
- la politique offline par criticité est fixée ;
- le plan de migration SQLite → PostgreSQL est défini ;
- les golden masters sont identifiés.

**VERDICT : WEB-0 AUDIT DE PRÉSERVATION ACQUIS — PASSAGE À LA FONDATION TECHNIQUE AUTORISÉ, SANS PORTAGE MÉTIER AVANT LES GATES D’ARCHITECTURE.**
