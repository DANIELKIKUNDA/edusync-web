# EduSync Web — Point 4A — Portage Paramètres

Date: 2026-09-12

## Verdict

**IMPLEMENTATION LOCALE SOLIDE — PARAMÈTRES WEB PORTÉS EN FONDATION MÉTIER, CERTIFICATION POSTGRESQL/NAVIGATEUR RÉELLE RESTANTE.**

Le lot applique la doctrine preservation-first : il ne redéfinit pas le métier des Paramètres Desktop. Il transforme les concepts certifiés en modèle Web multi-école, versionné, audité et isolé par `school_id`.

## Addendum Point 3B inclus

Deux rôles standards Secondaire ont été ajoutés avant le portage :

- `DIRECTEUR_ETUDES` : Secondaire uniquement, suivi pédagogique/scolaire, Finance exclue de la baseline et ajoutable explicitement en lecture via RBAC.
- `DIRECTEUR_DISCIPLINE` : Secondaire uniquement, suivi quotidien des élèves et communication forte avec parents (individuel, classe, section, SMS), sans Finance par défaut.

Le trigger PostgreSQL de scope refuse leur affectation standard hors `SECTION=SECONDAIRE`.

## Paramètres portés

Le backend expose maintenant un Centre de configuration Web avec 25 routes OpenAPI couvrant : identité école, readiness progressive, catalogue RDC, années scolaires, sections, options, classes, types de frais, tarifs, politiques versionnées, contributions en nature et articles scolaires.

Les années scolaires suivent un cycle explicite `PREPARED -> ACTIVE -> CLOSED -> ARCHIVED`, avec réouverture explicite vers `PREPARED`. Une année CLOSED ne peut plus être réactivée directement.

La copie de configuration d'année reprend structure et tarifs vers une année cible PREPARED sans créer d'inscriptions, de charges ou de paiements.

Les tarifs sont strictement positifs. Une gratuité reste une décision financière distincte. Un index `NULLS NOT DISTINCT` empêche les doublons de tarifs actifs sur un même scope exact.

Les créations de classe et de tarif vérifient explicitement la cohérence tenant/année/section/option avant écriture ; RLS reste une défense supplémentaire.

## Zéro configuration lourde

Créer une école ne génère pas de classes réelles ni de tarifs inventés. Le provisioning crée seulement les références et defaults sûrs. Le readiness global reste informatif ; les prérequis bloquent uniquement le use case qui en dépend.

## Sécurité / cohérence

- RLS + `FORCE ROW LEVEL SECURITY` sur les tables tenant Paramètres.
- optimistic concurrency (`version`, `If-Match`).
- `Idempotency-Key` obligatoire sur les mutations critiques.
- audit + outbox pour les mutations exposées par l'API.
- aucune conversion implicite CDF/USD.
- RBAC Point 3 utilisé par l'IAM runtime : les nouveaux rôles ne sont pas uniquement documentaires.

## Frontend

Le frontend PWA contient déjà un Centre de configuration avec 13 rubriques, readiness, cycle d'années, activation des sections, ouverture de classes à partir du référentiel RDC, types de frais et vue tarifs. Les écrans finaux seront raffinés au Point 7 conformément à la feuille de route ; le Point 4 privilégie d'abord la parité métier et les contrats API.

## Ce qui reste hors verdict live

Cet environnement ne possède pas les dépendances frontend locales (`node_modules`) ni un PostgreSQL/Docker live. Le build TypeScript complet avec React types et les probes RLS réels restent donc dans le lot de certification machine/VPS. Une transpilation syntaxique TypeScript a toutefois été exécutée sur les sources applicatives.

Les opérations physiques de sauvegarde/restauration Web, historiques documentaires et sorties PDF/Excel riches restent volontairement raccordées au Point 5 Documents/Exports au lieu de reproduire les mécanismes SQLite Desktop.
