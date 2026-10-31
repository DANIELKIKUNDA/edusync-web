# Passe générale finale — EduSync Web en local (31/10/2026)

Version vérifiée : `main` = c9319f3 (toutes les branches de certification, la passe hors ligne, la passe mobile et la PR #29)
plus les correctifs de cette passe (branche `claude/passe-generale-finale`). Pile locale reconstruite sur cette version
(interface compilée, serveur redémarré, migrations appliquées) ; preuves PostgreSQL sur une base **neuve**
(`edusync_cert_final`). Aucune production touchée, aucun déploiement.

## 1. Résultats

| Domaine | Commande | Résultat |
|---|---|---|
| Backend complet | `cd backend && PYTHONUTF8=1 python -m pytest -q -p no:cacheprovider` | **1380 passed**, 1 skipped, 0 échec |
| Frontend (types + tests) | `cd frontend && npx tsc --noEmit -p . && npx vitest run tests --maxWorkers=2` | **91/91** |
| Registre des droits | `… env edusync_cert_final -- … tools/ci/rbac_registry.py check` | **0 dérive** |
| Trois rôles (Intendant, directeurs) — PostgreSQL réel | `tools/ci/three_roles_postgres_integration.py` | **178/178** |
| Secrétariat — PostgreSQL réel | `tools/ci/secretariat_postgres_integration.py` | **80/80** |
| Caissier — PostgreSQL réel | `tools/ci/cashier_postgres_integration.py` | **PASS** |
| Isolation des sections (Préfet, directions) — PostgreSQL réel | `tools/ci/section_isolation_postgres_integration.py` | **PASS** |
| Rejeux hors ligne — PostgreSQL réel | `tools/ci/offline_replay_postgres_integration.py` | **12/12** |
| **Mois exigé à l'inscription (PR #29) — PostgreSQL réel, nouveau** | `tools/ci/enrollment_month_postgres_integration.py` | **8/8** |
| Tests navigateur automatiques — application compilée | `EDUSYNC_TEST_BROWSER=msedge EDUSYNC_TEST_BUILD=1 node browser-tests/run.mjs --workers=1` | **23 passed**, 8 ignorés (mode développement) |
| Tests navigateur automatiques — mode développement | `EDUSYNC_TEST_BROWSER=msedge node browser-tests/run.mjs --workers=1 --timeout=60000` | **28 passed**, 3 ignorés (application compilée) |
| Recette Caissier | `node browser-tests/local_caissier_certification.mjs` | **0 échec**, aucune erreur HTTP |
| Recette Gestionnaire | `local_gestionnaire_certification.mjs` | **18/18** (15/18 avant le correctif G1) |
| Recette Préfet et directions de section | `local_section_leaders_certification.mjs` | **33/33** |
| Recette Intendant, directeurs, Secrétariat | `local_three_roles_certification.mjs` | **46/46** |
| Recette Responsable financier, Promoteur | `local_finance_roles_certification.mjs` | **25/25** |
| Hors ligne sur téléphone — Caissier / autres rôles | `local_offline_mobile_certification.mjs`, `local_offline_roles_certification.mjs` | **10/10**, **6/6** |
| Audit mobile — 12 rôles école + plateforme | `node browser-tests/local_mobile_audit.mjs` | **13 comptes, 100 écrans** : titre répété 0, débordement 0, tableau coupé 0, aucune erreur ; barre du bas propre à chaque rôle (caissier : Accueil · Encaisser · Élèves · Effectifs · Plus ; plateforme : Pilotage · Écoles · Accès · Équipe · Plus) |

## 2. Anomalies trouvées par cette passe et corrigées

| # | Anomalie | Correctif | Preuve |
|---|---|---|---|
| G1 | Le raccourci « Superviser les caisses » ouvrait le Centre financier sur **Recouvrement** au lieu de **Caisse** : l'écran demandé était lu **et effacé** pendant l'affichage ; un rendu jeté par React (partie encore en chargement) le consommait | L'écran demandé est lu sans être effacé, puis effacé une fois la page réellement affichée (`peekFinanceTarget` / `clearFinanceTarget`) | Recette Gestionnaire 15/18 → **18/18** ; Caissier (« Encaisser ») 0 échec |
| G2 | Ancien test `school_shell` (mobile) exigeait le fil d'Ariane sur un module principal, masqué par la passe mobile (titre unique) | Ordinateur : fil d'Ariane exigé ; téléphone : masqué, retour par « Accueil » de la barre du bas | 2 modes navigateur propres |
| G3 | Test `offline` (plateforme) instable sous charge : la copie complète de l'application en arrière-plan dépassait le délai de 5 s | Délai porté à 20 s, vérification inchangée | 3/3 seul, propre en série |
| G4 | `shared.spec` comptait 6 échecs sur l'application compilée — **défaut antérieur** (identique sur l'ancien `main` c34e16a) : sa page de test n'existe qu'en mode développement | Déclaré « mode développement uniquement » | 6/6 en mode développement |

## 3. Décisions du propriétaire appliquées le 31/10

- Tous les rôles école travaillent hors ligne (comptes, imports, annulations et clôture de journée restent en ligne).
- Mois exigé à l'inscription encaissable avant septembre — seul ce mois échappe à l'ordre (PR #29 fusionnée).
- CI de secours supprimée (PR #30 fermée, branche effacée) ; document de suivi du 27/10 fermé (PR #31).
- Passe mobile sur l'école **et** la plateforme ; petites cartes en blocs 2 × 2 ; onglet « Encaisser » pour qui encaisse.

Deux écrans gardent un premier contenu au-delà de 700 px : Communication de l'administrateur (mesure faussée : le contenu
est en haut, en blocs non repérés par le robot — vérifié sur capture) et Élèves du caissier (740 px : en-tête, chiffres et
recherche avant la liste). Aucun ne bloque l'usage.

## 4. Réserves — ce qui n'est pas « fini en local » et ne peut pas l'être par le code

| # | Réserve | Qui |
|---|---|---|
| R1 | CI GitHub non exécutée (facturation du compte bloquée) | Propriétaire |
| R2 | Essai de 10 minutes sur un **vrai téléphone Android** (hors ligne, inscription, encaissement, synchronisation) | Propriétaire |
| R3 | « Assistant du promoteur » : n'existe que comme modèle de rôle local (`SCHOOL_CUSTOM`), pas comme rôle standard — à garder ainsi ou à figer | Décision du propriétaire |

## 5. Avant une mise en production (repris de l'ancienne PR #31, toujours valable)

Version figée (SHA) ; CI réelle verte ; images Docker ARM64 par empreinte ; staging avec tests de bout en bout ; test de
**sauvegarde et restauration** ; HTTPS ; isolation entre écoles vérifiée en staging ; journalisation et supervision ;
feu vert explicite du propriétaire. Aucune de ces étapes n'est faite par cette passe locale.

## Conclusion

**EduSync Web est terminé et certifié en local** sur la version vérifiée : les 12 rôles école et la plateforme passent leurs
preuves PostgreSQL réelles, leurs recettes navigateur et l'audit mobile, sans anomalie ouverte dans le code (quatre
anomalies trouvées par cette passe, toutes corrigées et prouvées). Les seules réserves dépendent du propriétaire (CI GitHub,
essai sur un vrai téléphone, décision « Assistant du promoteur ») ; la suite relève des fonctionnalités à venir (parcours
scolaire et calcul des points) et de la mise en production (section 5).
