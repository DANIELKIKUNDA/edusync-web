# EduSync Web — pilotage des rôles et sortie du 01/11/2026

> **Document de coordination, non une certification.** Établi le 27/10/2026 à partir de `main`, du contrat `contracts/POINT3B_ROLE_DECISIONS_FINAL.json` et des PR visibles. La cible de sortie est le **01/11/2026** ; aucun GO automatique. Les preuves doivent être actualisées sur le SHA de livraison.

## 1. État des rôles : décision produit ≠ certification de livraison

| Rôle (code de référence) | Capacités contractuelles | Situation attestée au 27/10 | Prochaine action |
| --- | ---: | --- | --- |
| `CAISSIER` | 92 | Parcours principal considéré fermé par le propriétaire ; PR #18, #23, #25, #26, #28 fusionnées. PR #29 encore ouverte sur l'inscription / mensualité obligatoire. | Protéger la non-régression et statuer sur #29 ; ne pas rouvrir arbitrairement le rôle. |
| `ADMIN_SYSTEME_ECOLE` | 88 | Fermeture métier annoncée, PR #15 fusionnée. | Contrôles de non-régression sur SHA candidat. |
| `GESTIONNAIRE` | 118 | Fermeture métier annoncée, PR #24 fusionnée. | Préserver la doctrine supervision ; **interdiction de clôturer ou rouvrir une caisse**. |
| `PREFET_ETUDES` | 84 | **En développement**, PR #27 brouillon. Section Secondaire uniquement. | Terminer les cinq volets, tests positifs/négatifs et certification globale. |
| `DIRECTION_SECTION` | 84 | **En développement avec PR #27**, Maternelle, Primaire ou union explicite des deux. | Même clôture que Préfet, périmètres séparés. |
| `RESPONSABLE_FINANCE` | 67 | Contrat verrouillé, **aucune clôture récente vérifiée**. | Passage dédié lecture/contrôle financier, sans encaissement ni manipulation de caisse. |
| `PROMOTEUR` | 108 | Contrat verrouillé, **aucune clôture récente vérifiée**. | Consultation gouvernance/finance/export sans mutation métier ni envoi parent. |
| `ASSISTANT_PROMOTEUR` | — | **Blueprint SCHOOL_CUSTOM seulement**, pas un rôle standard figé. | Décider la combinaison/clonage effectif et certifier ses limites. |
| `DIRECTEUR_ETUDES` | 45 | Contrat verrouillé, **aucune clôture récente vérifiée**. | Secondaire uniquement ; finance hors baseline. |
| `DIRECTEUR_DISCIPLINE` | 41 | Contrat verrouillé, **aucune clôture récente vérifiée**. | Secondaire uniquement ; discipline et communication parents dans le scope. |
| `SECRETARIAT` | 24 | Contrat verrouillé, **aucune clôture récente vérifiée**. | Rôle minimal documentaire optionnel ; pas de finance par défaut. |
| `INTENDANT` | 29 | Contrat verrouillé, **aucune clôture récente vérifiée**. | Stocks, actifs, maintenance, inventaires et exports. |
| `MANAGER_SYSTEME` | 14 | Contrat plateforme verrouillé, **aucune clôture récente vérifiée**. | Vérification plateforme, activation des écoles, isolation inter-tenants. |

**Note :** `ASSISTANT_PROMOTEUR` n'appartient pas aux douze rôles standards du contrat ; il fait partie des modèles de rôle local. Les nombres sont ceux du contrat `main` au 27/10, pas les valeurs de documents historiques. Le mot « fermé » décrit la décision métier du propriétaire et des PR fusionnées, pas une preuve de production certifiée au SHA courant.

## 2. Chemin critique jusqu'au 01/11

**Aucune équipe ne doit multiplier les chantiers concurrents sur les mêmes fichiers.**

1. **PR #27 — priorité métier actuelle (Préfet / Directeur).** Branche `chatgpt/prefet-directeur-certification`. Conserver la PR en brouillon pendant les corrections. Contrat : `PREFET_ETUDES` = Secondaire, `DIRECTION_SECTION` = Primaire/Maternelle selon affectations, 84 capacités chacun. Un droit SECTION/CLASS n'accorde jamais SCHOOL par déduction. Lecture finance par section, jamais de caisse. Les cinq volets à traiter **ensemble** : documents/URLs signées avec provenance ; finances et exports filtrés ; parité de toutes les API scolaires ; PostgreSQL multi-sections/RBAC réel ; frontend authentifié (menus et routes directes).
2. **PR #30 — priorité infrastructure distincte.** Préparer une CI de secours lorsque GitHub Actions refuse le lancement faute de quota/facturation, puis restaurer un pipeline de vérification complet. Les tests locaux ne fournissent pas d'eux-mêmes les preuves CI/GHCR/déploiement exigées par le contrôleur sécurisé. **Ne jamais supprimer les gates de provenance, migrations ou rollback.**
3. **PR #29 — arbitrage ciblé, sans réouvrir tout le Caissier.** Vérifier ce changement avec les responsables de la finance et le métier, plus tests de non-régression POS/recouvrement ; ne pas fusionner sur la seule présence de tests statiques.
4. **Rôles encore non certifiés :** prioriser `RESPONSABLE_FINANCE`, puis `PROMOTEUR` et son assistant `SCHOOL_CUSTOM`, ensuite `DIRECTEUR_ETUDES`, `DIRECTEUR_DISCIPLINE`, `SECRETARIAT`, `INTENDANT`, en assurant en parallèle les fonctions critiques `MANAGER_SYSTEME` de plateforme. Les tâches peuvent être parallélisées **uniquement** sur fichiers/branches non chevauchants et avec les droits/contrats existants comme source normative.
5. **Candidat de production :** SHA figé, CI réelle, images Docker arm64 par digest, staging, E2E, tests de sauvegarde/restauration, HTTPS, isolation multi-écoles, journalisation, approbation. Pas de certification par héritage d'un commit antérieur.

## 3. Ordre de contrôle transversal de chaque rôle

| Gate | Preuve minimale |
| --- | --- |
| CONTRAT | Capacités exactes du JSON officiel, mandat métier, périmètre et opérations interdites. |
| API / SQL | Tests fonctionnels et négatifs, 403/404 hors périmètre, listes + détails + exports, PostgreSQL réel. |
| FRONTEND | Connexion réelle, menus, écrans, navigation directe, téléphone, erreurs, export/impression. |
| NON-RÉGRESSION | Aucun affaiblissement des rôles clos ; monnaie affichée **FC / USD** (jamais « CDF » dans l'UI), dates **JJ/MM/AAAA**. |
| INTÉGRATION | Tests serveur et navigateur, migrations, sécurité, preuves du **SHA exact**. |
| STAGING | Tests de services complets, sauvegarde vérifiée, rollback, parcours métier et supervision. |
| GO | Aucune faille critique, aucune gate obligatoirement BLOCKED ; feu vert explicite du propriétaire. |

Séparer `PASS`, `FAIL`, `BLOCKED`, `NOT APPLICABLE`. Une fonctionnalité qui refuse tout accès par prudence est **sécurisée mais non livrée** lorsqu'elle devrait être disponible selon le contrat.

## 4. Calendrier et décision de sortie

| Date | Critère objectif |
| --- | --- |
| 27/10 | Suivi des trois PR ouvertes, CI de secours revue, périmètre exact de #27 connu. |
| 28/10 | Corrections de #27 en cours ; tests backend/frontend/SQL réellement exécutés. |
| 29/10 | Achèvement des fonctions autorisées et preuves RBAC, audits des rôles prioritaires restants. |
| 30/10 | Publication des images certifiées + staging et E2E réels pour le SHA candidat. |
| 31/10 | Rapport de préparation GO/NO-GO signé ; blocages et fonctionnalités à différer **explicitement** documentés. |
| 01/11 | Mise en production **uniquement si GO**. Sinon, lancement limité exclusivement aux fonctionnalités certifiées et non exposées aux rôles inachevés, après approbation de portée et validation de la sécurité, ou report. |

Il est **interdit** de présenter une mise en production partielle comme une certification complète de tous les rôles.

## 5. Précautions de coordination

- Conserver `main` et toutes les migrations stables pendant les audits.
- Ne pas écraser les 100+ commits actifs de PR #27 ni les travaux en cours de Codex/Claude sur cette branche.
- Découper par domaine et faire une seule fusion contrôlée après revue ; pas de `force push`.
- Le VPS Hetzner ARM64 (8 Gio / 80 Go) sert déjà d'environnement d'applications : ne pas lancer d'essais destructeurs ou lourds sans mesure de capacité et isolation.
- La préparation documentaire et les audits GitHub ne signifient pas que le serveur a été touché : **aucune commande Hetzner exécutée dans ce document**.

### Pointeurs

- PR #27 (en développement) : https://github.com/DANIELKIKUNDA/edusync-web/pull/27
- PR #29 (correctif inscription) : https://github.com/DANIELKIKUNDA/edusync-web/pull/29
- PR #30 (CI de secours) : https://github.com/DANIELKIKUNDA/edusync-web/pull/30
- `docs/rbac/ROLE_SECTION_LEADERSHIP_UNIFIED_DELIVERY_AND_CERTIFICATION.md` (branche de PR #27)
- `PRODUCTION.md`, `CICD.md` (gates de livraison)
