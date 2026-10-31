# Certification du rôle Secrétariat — rapport (31/10/2026, pile locale)

Branche : `claude/secretariat-certification` (issue de `chatgpt/intendant-etudes-discipline-certification`, qui contient
déjà les branches PR #27 et Responsable financier / Promoteur). Aucune fusion, aucun déploiement, aucune PR ouverte.

## 1. Périmètre du rôle

Décision du 24/10/2026 : « en RDC, le caissier est généralement aussi le secrétaire » — le **Caissier détient tous les
droits du Secrétariat** et il est déjà certifié (PostgreSQL réel inclus). Cette certification prouve le Secrétariat
**seul**, sans aucun droit financier.

| Lifecycle | Nombre | Traitement |
|---|---|---|
| ACTIVE | 28 | Exécutés sur PostgreSQL réel (`tools/ci/secretariat_postgres_integration.py`) et dans le navigateur |
| ALIAS | 6 | Couverts par leur droit métier (PDF / Excel / impression = un seul droit d'export) |
| DEPRECATED | 2 | N/A justifié (`enrollments.read`, `families.responsibles.read` : aucun code ne les contrôle) |
| PLANNED | 1 | N/A justifié (`documents.regenerate` : aucune route ne l'utilise) |

Ce que fait le Secrétariat : lire les élèves, les familles, les effectifs (par classe et par section), les réglages ;
imprimer et exporter les annuaires, les fiches élèves et les effectifs ; **compléter** la fiche d'un élève (jamais corriger
son identité) ; **créer et modifier** les dossiers du personnel (jamais suspendre, sortir ni affecter) ; **importer** des
élèves depuis le modèle officiel ; **préparer** les modèles de messages (jamais envoyer).

## 2. Audit de sécurité

Carte « droit → routes » établie sur le code : chaque droit actif est contrôlé côté serveur. Deux rapprochements suspects
ont été vérifiés et écartés (la route d'exécution de la reprise financière exige bien `migration.finance_history.execute`,
`PUT /settings/billing-policy` exige bien `settings.billing_months.manage`). **Aucune faille serveur.**

## 3. Anomalies trouvées et corrigées

| # | Anomalie | Correctif |
|---|---|---|
| S1 | Écran Personnel : le catalogue des fonctions était demandé dès qu'on pouvait **créer** un agent, alors que le serveur exige `personnel.functions.read` → refus 403 à chaque ouverture (Secrétariat **et Caissier**) | Catalogue chargé seulement avec son droit de lecture |
| S2 | Formulaire « Ajouter un agent » : bloc « Affectation initiale » proposé au Secrétariat et au Caissier, qui n'ont pas `personnel.assignments.add` (le serveur l'aurait refusé) | Bloc affiché seulement avec le droit d'affecter ; sinon une phrase claire : le gestionnaire du personnel affectera l'agent |
| S3 | « Dossiers élèves suffisamment complétés » (écran Élèves) calculé sur la **seule page chargée** de l'annuaire, pas sur toute l'école | Comptage fait par le serveur (`profiles_to_complete` dans `/schooling/summary`, périmètre du lecteur appliqué) |
| S4 | Accueil du Secrétariat muet sur son vrai travail | Nouvelle carte « Dossiers élèves à compléter » (droits `students.profile.complete` + `students.read`) et constat dans « Le point du jour » |

## 4. Exécution des tests

| Suite | Commande | Résultat |
|---|---|---|
| PostgreSQL réel, Secrétariat seul | `python tools/local/isolated_db.py create edusync_cert_secretariat` puis `… env edusync_cert_secretariat -- ../.venv/Scripts/python.exe ../tools/ci/secretariat_postgres_integration.py` | **80/80 PASS** |
| Recette navigateur | `cd frontend && node browser-tests/local_three_roles_certification.mjs secretariat` | **13/13 PASS** (connexion, accueil, point du jour cliqué, annuaire exporté, Personnel, Communication, chaque module et onglet, responsive 320 → 1440 px) |
| Non-régression Caissier (navigateur) | `cd frontend && node browser-tests/local_caissier_certification.mjs` | **0 échec**, aucune erreur HTTP (le correctif Personnel S1/S2 touche aussi le Caissier) |
| Robot d'exploration | `cd frontend && node browser-tests/local_audit_robot.mjs ../.local/secretariat/.account.json 1440` | **0 constat** (un passage lancé pendant une recompilation ou sous forte charge avait signalé des erreurs de chargement et un clic expiré ; non reproductibles, relancé seul : 0) |
| Tests frontend | `cd frontend && npx vitest run tests --maxWorkers=4` | **86/86** (dont `tests/secretariat_personnel.test.tsx`, 3 nouveaux) ; `tsc --noEmit` propre |
| Backend complet | `cd backend && PYTHONUTF8=1 python -m pytest -q -p no:cacheprovider` | **1375 passed**, 1 skipped, 0 échec ; registre : 0 dérive |

Contenu de la preuve PostgreSQL : périmètre du registre (aucun droit financier, d'inscription ni d'envoi) ; 18 lectures ;
14 fichiers réels (PDF `%PDF`, Excel `PK`) ; fiche élève complétée avec audit, version périmée → 409, identité → 403 ;
agent créé, modifié (If-Match), doublon de matricule refusé, suspension et sortie → 403 ; modèle de message créé, variable
inconnue refusée, aperçu, envoi refusé pour toutes les audiences et aucun message parti ; import du modèle officiel :
analyse sans écriture, confirmation des foyers exigée, 2 élèves créés, rejeu sans doublon ; 8 opérations interdites → 403
et 5 lectures non accordées → 403 sans aucune écriture ; isolation entre écoles (404, rien écrit) ; retrait d'un droit par
l'école → 403.

## 5. Réserves

| # | Réserve | Nature |
|---|---|---|
| R1 | CI GitHub non exécutée (facturation du compte bloquée) | Hors de portée du code |

## Conclusion

**Secrétariat certifié en local** : 37 droits traités (28 exécutés, 6 alias couverts, 3 N/A justifiés), aucune faille serveur, 4 anomalies d’interface corrigées (dont 2 qui touchaient aussi le Caissier), 80 contrôles sur PostgreSQL réel, recette navigateur et robot sans constat. Tous les rôles école sont désormais certifiés en local ; prochaine étape du plan validé le 30/10 : la preuve du hors-ligne sur téléphone.
