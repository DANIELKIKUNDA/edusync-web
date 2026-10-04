# Point 4C — Rapport d'implémentation corrigé

## Périmètre

Port du module **Élèves / Familles / Inscriptions** vers EduSync Web/PWA en doctrine **préservation d'abord**.

## Correction de préservation

Après comparaison directe avec le code Desktop certifié, la couche Documents a été corrigée pour reprendre les colonnes, ordre, filtres et présentation métier existants au lieu de proposer un export simplifié.

Le document `POINT4C_PRESERVATION_CORRECTION.md` décrit le delta et rend le premier checkpoint Point 4C obsolète.

## Backend

- PostgreSQL `0013_schooling_domain.sql` + migration `0014_preservation_school_identity_and_enrollment.sql` ;
- identité école enrichie avec adresse, ville, province afin de reproduire les en-têtes officiels ;
- foyers, responsables, liens foyer-responsable, élèves, inscriptions, affectations classe, événements de statut, avantages, résolution de foyer ;
- RLS + FORCE RLS ;
- idempotence, audit, outbox et concurrence optimiste ;
- contrôle de périmètre école/section/classe ;
- recherches/exports filtrés selon année, section, classe, statut et sexe.

## Inscription terrain

Par défaut, les **5 champs bloquants** sont : Nom, Postnom, Prénom, Sexe, Classe.

Date de naissance, lieu de naissance et autres compléments restent éditables ultérieurement. Les règles plus strictes doivent provenir d'une politique explicite de l'école.

## Familles et responsables

- Famille/Foyer et Responsable restent deux concepts séparés ;
- code famille permanent ;
- responsable principal distinct ;
- libellé de foyer générable automatiquement ;
- recherche assistée ;
- aucune fusion silencieuse ;
- familles nombreuses, bénéficiaires et enfants du personnel conservés comme vues métier distinctes.

## Documents préservés

### Liste des élèves

`N° | Matricule | Élève | Sexe | Année | Section | Classe | Date naissance | Lieu naissance | Responsable / foyer | Téléphone | Statut`

### Répertoire des familles

`Code famille | Famille / foyer | Responsable principal | Téléphone | Adresse | Enfants inscrits`

Les sorties reprennent l'identité de l'école, le logo lorsqu'il est disponible, les coordonnées, le titre centré, le périmètre de consultation, la date d'édition, le total, l'en-tête bleu certifié et la présentation paysage.

## Frontend

La modernisation Web est additive : KPI, navigation, drawer, recherche, responsive et micro-animations. Elle ne change pas les données métier ni la structure des documents certifiés.

## Verdict local

**POINT 4C — PRESERVATION-CORRECTED LOCAL PASS.**

Le PostgreSQL/Docker/RLS réel, le build React complet et l'impression Windows restent dans le 1 % de certification machine/VPS.
