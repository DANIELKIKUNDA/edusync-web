# Certification — niveau « Administrateur système école » (24/10/2026)

Objectif du propriétaire : fermer définitivement les Paramètres et certifier, module par module, tout ce que
l’administrateur système d’une école peut faire, pour décider ensuite quels rôles confier à qui.

Méthode : un vrai administrateur (école C des données locales) fait le travail réel dans un vrai navigateur, branché sur
le vrai serveur et la vraie base (`frontend/browser-tests/local_admin_finition.mjs`, plus les parcours des passes 2 et 3).

## Ce que fait l’administrateur système, module par module

| Module | Ce qu’il voit et fait | État |
|---|---|---|
| Accueil | Progression du paramétrage (100 % quand tout ce qui s’applique est prêt), cartes « À suivre » cliquables, activité récente | Certifié |
| Paramètres — École & identité | Nom, coordonnées, devise, logo ; numérotation automatique (prochain matricule, famille, reçu) | Certifié |
| Paramètres — Années scolaires | Préparer, activer, clôturer, archiver, rouvrir ; **période d’inscription** à la création, modifiable ; hors période, l’inscription reste possible et est signalée au secrétariat | Certifié |
| Paramètres — Structure & classes | Sections, options en Humanités, ouverture en lot avec **parallèles par niveau** | Certifié |
| Paramètres — Inscriptions, Avantages | Conditions d’admission, avantages sur plusieurs frais, exonérations individuelles via Finance | Certifié |
| Paramètres — Types de frais | Modèles, frais personnalisé, modifier / désactiver depuis la ligne | Certifié |
| Paramètres — Tarifs & barèmes | Assistant : grille par niveau, règle sur plusieurs cibles, frais réglementaires ; « Appliquer » met en attente, **un seul « Tout enregistrer »** à la sortie ; confirmation si on quitte avec des règles non enregistrées | Certifié |
| Paramètres — Encaissement, Plans anticipés | Règles de caisse ; un plan anticipé vise **une ou plusieurs classes, niveaux ou sections** | Certifié |
| Paramètres — Contributions, Articles scolaires | Articles : **prix de vente unitaire, stock de départ, seuil d’alerte**, valeur du stock, alertes rupture / stock bas ; entrées et corrections tracées (rôle Intendant) ; la caisse retire le stock à la vente | Certifié |
| Paramètres — Documents & signature, Sauvegardes & diagnostic | Signataire et logo des PDF ; copie vérifiée des données de l’école, test, diagnostic sans données personnelles | Certifié |
| Documents | Documents générés avec versions ; catalogue cliquable (chaque type ouvre ses documents) ; logo et impression | Certifié |
| Communication | L’administrateur **pilote** : canaux de l’école (interrupteurs), solde SMS, notifications de l’appareil, et voit **qui peut écrire aux familles** d’après les vrais rôles de l’école. La rédaction des messages revient aux rôles autorisés (préfet, directeurs…) | Certifié |
| Synchronisation | En langage simple : envois en attente, appareils autorisés (autoriser / révoquer avec confirmation), cas à arbitrer, opérations refusées ; cartes cliquables | Certifié |
| Accès & rôles | Membres, rôles, demandes, journal ; garde-fous ; cartes chiffrées cliquables | Certifié |

Finitions transverses : indicateur de chargement centré dans la zone de travail (anneau animé, texte lisible), icônes sur
toutes les cartes, toutes les cartes chiffrées ouvrent ce qu’elles comptent.

## Rôles standards de l’école — droits actifs par domaine

Tableau généré depuis le registre canonique `contracts/CAPABILITY_REGISTRY.json` (rôles décidés par le propriétaire).
Il aide à choisir qui reçoit quel rôle ; chaque école peut ensuite ajuster un rôle standard (Accès & rôles).

| Rôle | Utilisateurs & accès | Audit | Notifications & communications | Effectifs & dépôts | Documents | Élèves & inscriptions | Centre financier | Intendance | Migration & import | Personnel | Paramètres | Synchronisation & offline | Total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Administrateur système école | 9 | 3 | 4 | — | 2 | — | 2 | — | — | 2 | 47 | 5 | 74 |
| Caissier | — | — | 2 | 4 | 3 | 17 | 31 | — | 2 | — | 7 | 1 | 67 |
| Directeur de discipline | — | 1 | 10 | 5 | 2 | 6 | — | — | — | — | 3 | — | 27 |
| Directeur des études | — | 1 | 9 | 6 | 2 | 6 | — | — | — | — | 3 | — | 27 |
| Directeur / Directrice de section | — | 1 | 10 | 6 | 2 | 14 | 16 | — | 2 | 7 | 5 | — | 63 |
| Gestionnaire | — | 3 | 3 | 9 | 2 | 7 | 31 | 5 | 2 | 17 | 11 | — | 90 |
| Intendant | — | 1 | 2 | — | 2 | — | — | 14 | — | 1 | 1 | — | 21 |
| Préfet des études | — | 1 | 10 | 6 | 2 | 14 | 16 | — | 2 | 7 | 5 | — | 63 |
| Promoteur | — | 3 | 3 | 9 | 2 | 7 | 24 | 5 | 2 | 8 | 11 | — | 74 |
| Responsable chargé des finances | — | 3 | 1 | — | 2 | 4 | 25 | — | 2 | — | 7 | — | 44 |
| Secrétariat | — | — | 6 | 4 | 2 | 6 | — | — | — | 3 | 4 | — | 25 |

Lecture rapide pour décider :
- **Administrateur système** : paramètre l’école et gère les accès ; il n’encaisse pas et n’inscrit pas d’élèves
  (séparation des tâches).
- **Secrétariat** : inscriptions, dossiers, modèles de messages.
- **Caissier** : encaissements, reçus, ventes d’articles.
- **Intendant** : stock (entrées, sorties, inventaires) et matériel.
- **Préfet des études / Directeur de section** : pédagogie, effectifs, communication aux familles, suivi financier.
- **Gestionnaire / Promoteur / Responsable des finances** : pilotage, rapports, contrôles et décisions financières.

## Preuves

- `local_admin_finition.mjs` : **13 étapes sur 13** (deux fois de suite, aucune erreur serveur). Couverture : 100 %
  de paramétrage, période d’inscription, article avec stock puis changement de prix, plan sur deux classes, assistant
  tarifaire en un seul enregistrement (trois sources : grille de deux frais et frais réglementaires), confirmation à la
  sortie, communication (cartes et interrupteurs), synchronisation (appareil autorisé), documents (catalogue cliquable),
  accès & rôles (carte chiffrée).
- pytest : 942 réussis ; Vitest : 58 réussis.

Reste hors de cette passe, à la demande du propriétaire : l’impression directe (sans fenêtre) des reçus.
