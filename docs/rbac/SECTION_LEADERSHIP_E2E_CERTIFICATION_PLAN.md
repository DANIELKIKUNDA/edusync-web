# Certification E2E — Préfet et Directeurs (primaire, maternelle)

**Statut : NON CERTIFIÉ.** Cette matrice définit les scénarios HTTP + PostgreSQL à automatiser et exécuter avant toute fusion. Les tests unitaires seuls ne constituent pas une preuve E2E.

## Environnement et prérequis
- PostgreSQL de test isolé, migrations réelles, API FastAPI démarrée avec authentification réelle.
- Trois sections (SECONDAIRE, PRIMAIRE, MATERNELLE), plusieurs classes et deux écoles distinctes.
- Utilisateurs réels : préfet secondaire, directeur primaire, directeur maternelle, administrateur SCHOOL, responsable cumulant deux sections, responsable CLASS, utilisateur révoqué.
- Utiliser des données fictives. Chaque scénario lit aussi directement PostgreSQL pour vérifier l'absence d'écritures non autorisées, l'audit et l'outbox.
- Chaque requête de mutation utilise une clé Idempotency-Key unique; les PUT utilisent If-Match. Répéter les requêtes avec la même clé et vérifier l'absence de doublon.

## Scénarios bloquants

| ID | Parcours HTTP de bout en bout | Attendu |
|---|---|---|
| E2E-01 | Préfet connecté : annuaire, fiche agent secondaire | 200, uniquement affectations secondaires, aucun lien familial ou compte global |
| E2E-02 | Préfet : agent primaire/maternelle et accès direct par UUID | 403/404, aucune donnée |
| E2E-03 | Directeur primaire : annuaire et fiche d'un agent partagé primaire/secondaire | Détails limités au primaire; aucune affectation secondaire |
| E2E-04 | Préfet : création d'agent avec affectation secondaire valide | 201, staff + assignment + audit/outbox atomiques |
| E2E-05 | Préfet : création sans affectation, affectation primaire, ID de section d'une autre école, classe incohérente | 403/4xx, aucune ligne staff/assignment/audit |
| E2E-06 | Préfet : création avec function_id d'une autre école | 4xx, aucune écriture |
| E2E-07 | Directeur primaire : ajout d'affectation primaire à un agent visible | 201, une affectation, audit |
| E2E-08 | Directeur primaire : ajout affectation secondaire, SCHOOL, ou primaire à agent hors périmètre | 403, aucune écriture |
| E2E-09 | Directeur primaire : modification agent exclusivement primaire avec If-Match correct | 200, version +1, audit |
| E2E-10 | Directeur primaire : modification agent partagé primaire/secondaire ou global | 403, identité inchangée |
| E2E-11 | Responsable double section : lecture, création, affectation, modification dans les deux sections | Autorisé seulement dans l'union des deux sections |
| E2E-12 | Permission SCHOOL sur lecture mais SECTION sur écriture | Lecture large, écriture strictement limitée |
| E2E-13 | Responsable CLASS : classe autorisée vs classe voisine et titulariat hors classe | Refus hors classe |
| E2E-14 | Utilisateur révoqué : réutilisation du jeton/session, puis nouvel accès | Aucun accès après révocation effective |
| E2E-15 | Deux écoles avec UUID et codes de section similaires | Aucune fuite ni écriture inter-écoles |
| E2E-16 | Deux requêtes concurrentes : ajout affectation secondaire et modification identité primaire | Pas de TOCTOU; la modification primaire est refusée ou sérialisée |
| E2E-17 | Échec artificiel de l'insertion d'affectation après création du staff | Rollback intégral (staff, audit, outbox) |
| E2E-18 | Idempotence : double POST création/affectation et double PUT | Une seule mutation; réponse de rejeu stable |
| E2E-19 | If-Match périmé / deux modifications concurrentes | 409/412, aucune perte de mise à jour |
| E2E-20 | Exports, rapports, recherche, pagination, accès direct UUID | Même isolation que l'annuaire |
| E2E-21 | Fonction de direction : responsable qui reçoit une permission personnalisée additionnelle | Le périmètre est vérifié par capacité, sans élargissement transversal |
| E2E-22 | Contrôles finance, documents, scolarité, famille et historique des rôles | Aucun élargissement indirect par relation ou export |

## Gates de sortie
1. Tous les tests E2E passent sur une base PostgreSQL migrée et des jetons réels.
2. Tests unitaires, tests d'intégration et contrôle de type/lint passent sur le commit exact.
3. Rapport signé par SHA avec nombres PASS/FAIL/BLOCKED, journaux CI, tests de concurrence et contrôle multi-école.
4. Aucune fusion, aucun déploiement tant qu'un gate bloquant est FAIL ou BLOCKED.

## État des travaux
- Les tests unitaires de portée personnel ont été ajoutés sur la branche de certification.
- Les scénarios E2E ci-dessus **ne sont pas encore implémentés ni exécutés**. Ce document est une matrice de recette, pas une certification.
