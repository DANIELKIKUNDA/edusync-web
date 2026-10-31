# Preuve du hors-ligne sur téléphone — rapport (31/10/2026, pile locale)

Décisions du propriétaire : 25/10/2026 (« au niveau école, le système doit fonctionner sans internet puis synchroniser ;
l'inscription, la réinscription et les paiements ne doivent pas dépendre de la connexion ») et 30/10/2026 (plan de fin
locale, étape « preuve du hors-ligne sur téléphone »). Branche : `claude/offline-mobile-proof`. Aucune fusion, aucun
déploiement, aucune PR.

## 1. Le scénario prouvé

`frontend/browser-tests/local_offline_mobile_certification.mjs` — téléphone Android simulé (390 × 844, tactile, navigateur
mobile), application compilée avec son service worker, **vrai serveur et vraie base PostgreSQL**, compte Caissier :

1. connexion en ligne ; la copie locale (élèves + frais payables) est téléchargée ;
2. en ligne : la caisse du jour est clôturée, pour être rouverte sans réseau ;
3. **mode avion, application fermée puis rouverte sans réseau** : la session tient ;
4. hors ligne : **ouverture de caisse**, **inscription d'une famille** (section, classe, enfant), **encaissement** d'un élève
   retrouvé dans la copie locale (action conseillée) ;
5. le compteur « N en attente » s'affiche ; chaque opération a sa propre clé d'idempotence ;
6. **retour du réseau, et la première réponse du serveur à l'inscription et à l'encaissement est perdue en route** (le
   serveur enregistre, le téléphone ne reçoit rien) ; synchronisation automatique, dans l'ordre ;
7. **base de données : 1 élève, 1 inscription, 1 paiement par clé — jamais 0, jamais 2** ;
8. l'élève inscrit hors ligne est visible en ligne, rien « à vérifier », aucun débordement d'écran.

Résultat : **10/10 PASS**, deux passages consécutifs.

## 2. Défauts trouvés par cette preuve et corrigés

Sans ces correctifs, **une école sans réseau ne pouvait pas travailler sur téléphone**.

| # | Défaut | Correctif |
|---|---|---|
| H1 | Un module jamais ouvert en ligne (Centre financier, Élèves…) ne s'ouvrait pas hors ligne : son code n'était gardé qu'après un premier chargement | À chaque compilation, la liste complète des modules est inscrite dans le service worker (`vite.config.ts`, `public/sw.js`) ; le téléphone télécharge toute l'application en arrière-plan après la première connexion (2,3 Mo, une fois par version). Le service worker s'active d'abord avec le squelette, pour qu'une coupure pendant le téléchargement ne laisse jamais le téléphone sans application |
| H2 | Bandeau hors ligne de l'école : « lecture seule… Aucune modification n'est mise en attente » — contraire à la décision du 25/10 et faux | Bandeau propre à l'école : « Hors connexion — vous pouvez continuer. Inscriptions, réinscriptions, encaissements, dépenses et dépôts sont enregistrés sur cet appareil et envoyés automatiquement au retour du réseau… » (la plateforme reste en lecture seule) |
| H3 | Inscription hors ligne : choix de section et de classe vide si l'écran Élèves n'avait pas été ouvert en ligne | Les classes, années et options sont lues en arrière-plan pendant que le réseau est là, pour tout rôle qui inscrit ou réinscrit (`useEnrollmentReference`) |
| H4 | Écran Élèves : une seule liste manquante hors ligne (une page de l'annuaire) faisait échouer tout le chargement, classes comprises | Les quatre lectures sont indépendantes ; ce qui est disponible s'affiche |
| H5 | « Action conseillée » sans effet hors ligne (elle interroge le serveur) | Calculée sur la copie locale avec l'ordre du serveur (le plus ancien frais payable) ; le serveur revérifie tout à la synchronisation |
| H6 | Compteur « N en attente » écrit mais affiché nulle part ; panneau « Sur cet appareil » (opérations en attente et refusées, avec la raison) accessible seulement dans le module Synchronisation (administration) — un caissier dont un paiement était refusé ne pouvait pas voir pourquoi | Compteur dans la barre du haut pour tout membre de l'école ; un toucher ouvre « Sur cet appareil » (feuille en bas d'écran sur téléphone) |
| H7 | Libellé de l'opération en attente « Encaissement · 1000 CDF » (aussi dans la notification « Synchronisé ») | « Encaissement · 1000 FC » |

## 3. Tests

| Suite | Commande | Résultat |
|---|---|---|
| Preuve hors ligne sur téléphone | `cd frontend && node browser-tests/local_offline_mobile_certification.mjs` | **10/10**, deux fois de suite |
| Hors ligne existants (école + plateforme), application compilée | `cd frontend && EDUSYNC_TEST_BROWSER=msedge EDUSYNC_TEST_BUILD=1 node browser-tests/run.mjs school_offline.spec.ts offline.spec.ts` | **2/2**, trois fois de suite |
| Tests frontend | `cd frontend && npx vitest run tests --maxWorkers=4` | **88/88** (dont `tests/offline_mobile_proof.test.ts`, 2 nouveaux) |

Le test « plateforme » vérifiait qu'aucune réponse du serveur n'est gardée en cache avec une règle qui repérait
« /health » n'importe où dans l'adresse : le module `/assets/health-….js`, désormais pré-chargé, déclenchait une fausse
alerte. La règle vise maintenant le début de l'adresse (`/api/…`, `/health`) ; la protection est inchangée.

## 4. Tous les rôles école travaillent hors ligne (décision du 31/10/2026)

Décision du propriétaire : « au niveau école tout le monde peut travailler offline ». Jusqu'ici, seules les opérations du
guichet (inscription, encaissement, vente, dépense, caisse, dépôt) étaient gardées sur l'appareil.

**Règle appliquée** : une opération est gardée hors ligne si le serveur sait la rejouer sans danger avec sa clé
d'idempotence (une réponse perdue ne crée jamais de doublon). La version de la fiche modifiée (`If-Match`) est gardée et
renvoyée au rejeu — elle était perdue auparavant.

| Désormais hors ligne | Rôles concernés |
|---|---|
| Fiche élève (compléter, corriger l'identité), abandon, suspension, transfert, réintégration, changement de classe, familles et responsables | Secrétariat, directeurs, préfet, direction de section, gestionnaire |
| Personnel : nouvel agent, fiche, statut, fonctions et affectations, enfants du personnel | Secrétariat, gestionnaire |
| Intendance : articles, entrées / sorties / corrections, patrimoine (fiche, état, réparation), inventaires (comptage, validation) | Intendant |
| Envoi de messages et modèles | Directeurs, préfet, secrétariat |
| Paramétrage de l'établissement | Administrateur |
| Fonds d'avance | Caissier |

**Volontairement réservé au réseau** (l'écran le dit) : comptes et accès (une désactivation doit être immédiate et
vérifiée), imports de fichiers (analyse sur le serveur), annulation de paiement, clôture et réouverture de la journée de
caisse, décisions financières (intégrité de la caisse), génération de documents, appareils de synchronisation.

**Défaut grave trouvé et corrigé** : la **dépense de caisse**, déjà gardée hors ligne, n'était pas reconnue par le serveur
au rejeu — après une réponse perdue, elle était **enregistrée deux fois** (caisse fausse). Six mises à jour de
l'intendance n'étaient pas sûres non plus (fiche article et fiche d'un bien : refus « modifié entre-temps » ; réparation :
intervention écrite deux fois ; validation d'inventaire : refus « déjà validé »). Toutes passent maintenant par le service
d'idempotence (clé facultative : sans clé, comportement inchangé). Preuve : `tools/ci/offline_replay_postgres_integration.py`
— **12/12** ; sur l'ancien code **5/12** (la dépense rejouée donnait 2 lignes).

Interface : bandeau « Ce que vous enregistrez est gardé sur cet appareil… », notification « Hors connexion : « … »
enregistrée sur cet appareil » sur les écrans qui ne le disaient pas, listes de travail de chaque rôle gardées à l'avance
(stock, patrimoine, inventaires, annuaire du personnel, choix d'affectation).

| Preuve | Commande | Résultat |
|---|---|---|
| Intendant (entrée de stock) et Secrétariat (nouvel agent), téléphone simulé, module jamais ouvert en ligne, réponse perdue | `cd frontend && node browser-tests/local_offline_roles_certification.mjs` | **6/6** — 1 mouvement, 1 dossier en base |
| Rejeux sur PostgreSQL réel | `… env edusync_cert_secretariat -- … ../tools/ci/offline_replay_postgres_integration.py` | **12/12** |
| Non-régression | backend complet ; trois rôles, caissier, secrétariat sur PostgreSQL réel ; caissier hors ligne | 1375 passed · 178/178 · PASS · 80/80 · 10/10 |
| Tests frontend | `npx vitest run tests --maxWorkers=4` | **91/91** |

## 5. Ce qui reste à faire par le propriétaire

La preuve est faite sur un téléphone **simulé**. Un essai de 10 minutes sur un **vrai téléphone Android** de l'école est
recommandé avant la mise en service : se connecter une fois avec le réseau, attendre une minute, passer en mode avion,
fermer complètement l'application, la rouvrir, inscrire un élève et encaisser un frais, puis réactiver le réseau et
vérifier que le compteur « en attente » revient à zéro et que l'élève et le reçu apparaissent.
