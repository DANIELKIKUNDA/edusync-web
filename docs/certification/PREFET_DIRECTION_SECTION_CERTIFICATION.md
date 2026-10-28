# Certification — Préfet du secondaire, Directeur du primaire, Directrice de la maternelle (PR #27)

Date : 28/10/2026 · Branche `chatgpt/prefet-directeur-certification` · base `main` fusionnée (`c34e16a`, sans conflit).
Statuts : **PASS** · **FAIL** · **BLOCKED** (non exécutable dans ce lot) · **NON CERTIFIÉ** (fonction volontairement fermée).
Aucune fusion, aucun déploiement. Les chiffres ci-dessous sont des résultats d'exécution réels sur la pile locale.

## 1. Comptes et périmètres testés

Comptes créés par l'écran « Ajouter un membre » (administrateur de l'école C), avec leur section :

| Compte | Rôle standard | Périmètre en base (`rbac_assignment_scopes`) |
|---|---|---|
| Préfet Secondaire | `PREFET_ETUDES` | `SECTION:SECONDAIRE` |
| Directeur Primaire | `DIRECTION_SECTION` | `SECTION:PRIMAIRE` |
| Directrice Maternelle | `DIRECTION_SECTION` | `SECTION:MATERNELLE` |
| Sonde double affectation | `DIRECTION_SECTION` | `SECTION:PRIMAIRE` + `SECTION:MATERNELLE` (union explicite, sans école) |
| Sonde « RH Secondaire » | `GESTIONNAIRE` limité | `SECTION:SECONDAIRE` (exerce le code d'écriture du personnel par section) |

Contrat appliqué (registre canonique, décisions 06 / 07) : les trois responsables ont le personnel **en lecture**
(annuaire, synthèse, historique, exports), pas de création / modification / affectation ; finance en lecture ; aucune
opération de caisse. Aucun droit n'a été ajouté.

## 2. Anomalies trouvées et corrigées

| # | Gravité | Anomalie | Correction |
|---|---|---|---|
| 1 | **Critique (isolation)** | « Ajouter un membre » attribuait toujours le périmètre **toute l'école** : un Directeur de section créé ainsi voyait toutes les sections ; un Préfet provoquait une erreur 500 (déclencheur SQL). « Attribuer un rôle » proposait aussi « Toute l'école » | API : les rôles de responsable de section (`PREFET_ETUDES`, `DIRECTION_SECTION`, `DIRECTEUR_ETUDES`, `DIRECTEUR_DISCIPLINE`) exigent une ou plusieurs sections (422 sinon), sections vérifiées dans une transaction école ; écran : choix des sections (plusieurs = double affectation), « Toute l'école » masqué |
| 2 | Haute | `500` sur « Familles & responsables » pour un responsable sans classe (liste SQL vide → `text = integer`) | Seules les listes non vides sont liées ; cas ajouté au test PostgreSQL réel de la CI (prouvé en échec sur l'ancien code) |
| 3 | Haute | Le formulaire « Ajouter un agent » exigeait fonction + affectation **aussi pour le Gestionnaire** : avec un catalogue de fonctions vide, plus personne ne pouvait créer d'agent (régression de la PR) | Affectation initiale obligatoire seulement pour un créateur limité à une section, comme l'API |
| 4 | Haute | Erreur de typage TypeScript (`personnel.tsx`) : le job « Frontend — typecheck » aurait échoué | Type `initial_assignment` aligné sur l'API (`SCHOOL` accepté) |
| 5 | Moyenne | Accueil : la carte Effectifs lisait les permissions dans le navigateur (contraire à la décision 9 du propriétaire) | Le serveur envoie `breakdowns` (section / classe / option) avec le widget |
| 6 | Moyenne | Accueil : cartes « Rapports officiels récents » et « Documents récents » affichées puis refusées (403) | Widgets marqués « périmètre école » côté serveur, non envoyés à un périmètre section |
| 7 | Moyenne | Personnel › Historique : 403 alors que le contrat donne `personnel.history.read` | L'historique global est servi **filtré** aux agents visibles de la section |
| 8 | Moyenne | Documents : 403 sur l'historique | Réponse vide + motif affiché (aucune archive exposée, voir § 6) |
| 9 | Moyenne | Rapports : « Synthèses par modèle » et « Rapports générés » proposés puis refusés | Sections masquées selon `generated_history_available` (même règle que l'API) |
| 10 | Moyenne | Effectifs : « Dépôts matériels » (carte et onglet) affiché sans le droit `contributions.register.read` (aussi sur `main`) | Affiché seulement avec le droit |
| 11 | Faible | « CDF » affiché (état vide du recouvrement) | « FC » |
| 12 | Faible | Liste « par option » : « Sans option » (Maternelle) en doublon | Options réelles ; « Section · sans option » seulement pour une section qui a des options |
| 13 | Faible | Catalogue de fonctions vide : impasse silencieuse pour un créateur de section | Message : le gestionnaire doit créer le catalogue |
| 14 | Tests | Tests de la branche cassés (rendu `POSTCOMPILE`, dataclass à slots) et tests de `main` sur l'ancien texte | Corrigés sans affaiblir leur intention |

## 3. Résultats

| Contrôle | Commande | Résultat |
|---|---|---|
| Tests backend | `python -m pytest -q` | **1290 passed**, 1 skipped, 0 échec |
| Tests frontend | `npx vitest run` | **80/80** |
| TypeScript / build | `npx tsc --noEmit` · `npx vite build` | **PASS** |
| PostgreSQL réel — isolation des sections | `tools/ci/section_isolation_postgres_integration.py` | **PASS** (dont indicateurs familles par section) |
| PostgreSQL réel — caissier | `tools/ci/cashier_postgres_integration.py` | **PASS** |
| Registre RBAC | `tools/ci/rbac_registry.py check` | **0 dérive** |
| Secrets · npm audit · compilation | `secret_patterns.py` · `npm audit --omit=dev` · `compileall` | **0 secret · 0 vulnérabilité · PASS** (dépendances identiques à `main`) |
| Sonde API réelle des 3 rôles | `tools/local/section_leaders_probe.py` | **96/96 PASS** |
| Recette navigateur des 3 rôles | `browser-tests/local_section_leaders_certification.mjs` | **33/33 PASS** |
| Non-régression Gestionnaire | `browser-tests/local_gestionnaire_certification.mjs` | **18/18 PASS** |
| Non-régression Caissier | `browser-tests/local_caissier_certification.mjs` | **0 échec** (script remis à jour : visionneuse PDF, « Compté FC ») |
| Robot d'exploration (Préfet, 1440 px) | `browser-tests/local_audit_robot.mjs` | 1er passage : anomalies 2, 6–10 ; 2e passage seul : 3 constats, tous sur un second accès à « Dépôts matériels » → corrigé et vérifié (aucun refus serveur) |

### Détail de la sonde API (extraits vérifiés contre la base)

- Effectifs : chaque responsable ne voit que sa section ; Total / Filles / Garçons **identiques** à la vue école
  (Gestionnaire). Secondaire : 36 = 28 F + 8 G ; option « Commerciale et gestion » 28 F · 8 G · 36 ; somme des
  options = effectif du secondaire. Maternelle : 16 (3 F · 13 G) au début de la recette, 20 après les inscriptions faites par la recette Caissier.
- Élèves : liste limitée à la section ; fiche et relevé financier d'un élève d'une autre section → 403/404 ; élève
  d'une autre école → 404.
- Personnel : annuaire limité aux agents de la section, aucune affectation d'une autre section exposée, synthèse
  sans compteur confidentiel ; fiche d'un agent d'une autre section → refus ; création / modification / affectation
  refusées aux trois responsables (lecture seule du contrat), **aucune ligne écrite**.
- Écriture par section (sonde « RH Secondaire ») : création dans sa section 201 ; autre section, sans affectation,
  « toute l'école » → refus et aucune ligne ; modification 200 ; version périmée 409/412 ; affectation dans une autre
  section ou « toute l'école » → 403.
- Gouvernance : `PREFET_ETUDES` / `DIRECTION_SECTION` sans section → 422, aucun compte créé ; double affectation
  Primaire + Maternelle → union exacte des deux sections.
- Finance : ouverture de caisse 403 ; rapport périodique filtré (200) ; rapport officiel PDF école → 403.

### Responsive

Accueil, Élèves et Personnel à 320, 390, 768, 1024 et 1440 px pour les trois comptes : aucun débordement horizontal
(captures `.local/section_leaders/cert`, mobile 390 px et tablette 768 px).

## 4. BLOCKED

| Point | Raison |
|---|---|
| CI GitHub sur le commit final | Tous les jobs refusés au lancement : « recent account payments have failed or your spending limit needs to be increased » (facturation du compte GitHub). Aucun résultat CI n'est revendiqué |
| Tests navigateur de composants (`npm run test:browser`) | Exécution locale perturbée par la saturation mémoire (17 réussis, 11 en échec pendant que le robot tournait) ; non rejoués seuls : **non certifiés** |
| Staging | Non déployé (la fusion déclenche le staging ; fusion non autorisée) |
| Primaire : parcours positifs sur des élèves | Aucun élève inscrit au Primaire dans le jeu de test : seuls les refus et les zéros sont vérifiés |
| Plan E2E : révocation en session active, concurrence (E2E-14, 16, 17) | Non exécutés dans ce lot |

## 5. Décision à confirmer par le propriétaire

La PR rend un agent affecté à **toute l'école** invisible aux responsables de section (règle plus stricte que le point
4B de `main`, où ils le voyaient en lecture). La règle stricte de la PR est conservée (« ne pas élargir ») ; le test
4B est amendé en conséquence. À confirmer : un Préfet doit-il voir, en lecture, les agents affectés à toute l'école ?

## 6. Fonctions volontairement fermées (NON CERTIFIÉES)

- **Historique documentaire** pour un périmètre section : les archives n'enregistrent pas leur section d'origine ;
  l'historique est vide avec un motif (aucune donnée exposée). Il faut persister la provenance (section, classe, objet)
  avant de l'ouvrir — point 1 du relais `docs/rbac/CLAUDE_HANDOFF_SECTION_ISOLATION_20261027.md`.
- **Rapports officiels PDF et registre des rapports générés** : réservés au périmètre école ; l'aperçu périodique est,
  lui, filtré par section.

## 7. Conclusion sur l'aptitude à la fusion

Le code de la branche corrigée est **apte sur le plan fonctionnel et sécurité** pour les trois responsables : isolation
vérifiée sur base réelle et par l'API, aucune régression sur le Gestionnaire et le Caissier, toutes les suites locales
vertes. La PR **n'est pas encore fusionnable** : il faut (1) une CI GitHub verte sur le commit final (bloquée par la
facturation), (2) la confirmation du § 5, (3) rejouer seuls les tests navigateur de composants. Les fonctions du § 6 restent
fermées et signalées.
