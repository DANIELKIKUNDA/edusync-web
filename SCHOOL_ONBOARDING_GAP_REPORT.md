# Mise en service d'une école — écarts

Date : 2026-10-14. Question : une école nouvellement créée par la plateforme peut-elle se mettre en service seule,
sans aide technique et sans données fictives ?

## 1. Parcours réel (état après N2)

| # | Étape | Qui | Où | État |
|---|-------|-----|----|------|
| 1 | Création de l'école | plateforme | Atelier Pro › Écoles | EXISTANT (N1) |
| 2 | Création de l'administrateur initial | plateforme | Atelier Pro › action « administrateur initial » | EXISTANT (N1) ; changement de mot de passe à la 1re connexion = **OWNER_DECISION O1** |
| 3 | Première connexion de l'administrateur | école | Connexion | EXISTANT |
| 4 | Voir ce qui reste à faire | école | Paramètres › Mise en service : « Prochaine étape » + « Continuer » | **construit en N2** |
| 5 | Identité et logo | école | Paramètres › École & identité | **refait en N2** (logo vérifié, coordonnées groupées) |
| 6 | Année scolaire : préparer puis activer | école | Paramètres › Années | **refait en N2** (année suivante proposée, confirmations) |
| 7 | Sections, options, classes | école | Paramètres › Structure | **refait en N2** (options ajoutées, classes filtrées par section) |
| 8 | Règles d'inscription | école | Paramètres › Inscriptions | **construit en N2** |
| 9 | Types de frais puis tarifs | école | Paramètres › Types de frais, Tarifs | EXISTANT, montants formatés en N2 |
| 10 | Équipe : créer les comptes, attribuer les rôles | école | Accès & rôles | **construit en N2** (mot de passe provisoire, changement obligatoire) |
| 11 | Première inscription d'élève | école | Élèves & inscriptions | EXISTANT (N3) |

Vérifié dans le navigateur sur l'école C de la base de certification (incomplète) : la mise en service propose
« Prochaine étape : Année scolaire » et « Continuer » ouvre la section Années (captures
`settings-readiness-C-390.png`, `settings-readiness-next-C-390.png`).

## 2. Écarts restants

| # | Écart | Statut | Proposition |
|---|-------|--------|-------------|
| E1 | L'équipe (étape 10) n'apparaît pas dans la liste de préparation : elle est calculée par le serveur et ne compte que la configuration | PARTIEL | ajouter un point « Équipe » côté serveur (au moins un second compte actif) — à décider, car une petite école peut fonctionner avec un seul compte |
| E2 | Pas d'assistant pas à pas facultatif pour une école qui part de zéro | ABSENT | assistant qui enchaîne les sections dans l'ordre de la liste, sans jamais bloquer ; N3 |
| E3 | Invitation par e-mail ou SMS | BLOCKED_EXTERNAL | dépend d'un fournisseur réel (OWNER_DECISION O4) |
| E4 | Import de la structure depuis le fichier de l'année précédente | EXISTANT côté serveur (copie de classes et tarifs vers une nouvelle année) ; pas d'écran dans les Paramètres | écran « Reprendre la structure de l'année précédente » ; N3 |
| E5 | Politiques autres que l'inscription | À CONFIRMER | sans écran tant qu'aucun module ne les applique (OWNER_DECISION O3) |
| E6 | Notifications internes : point « À confirmer » de la liste de préparation sans écran de réglage | PARTIEL | écran de réglage simple ; N3 |

## 3. Conclusion

Une école peut se mettre en service seule pour l'essentiel : identité, année, structure, règles d'inscription,
frais, tarifs et équipe, sans donnée fictive et sans blocage global. Les écarts restants sont des conforts (assistant,
reprise de l'année précédente) ou dépendent d'un fournisseur externe ou d'une décision du propriétaire.

## 4. Écarts relevés au N1 (version précédente de ce rapport) et statut après N2

Ce rapport remplaçait la version N1 du même fichier ; ses six écarts sont repris ici pour garder la trace.

| # N1 | Écart N1 | Statut après N2 |
|------|----------|-----------------|
| 1 | La plateforme ne réinitialise pas le mot de passe d'un administrateur d'école | **toujours ouvert** (OWNER_DECISION). Atténué en N2 : un administrateur d'école peut désormais réinitialiser un autre membre de son école (mot de passe provisoire + sessions coupées, D4) |
| 2 | `platform.schools.update` sans route : la plateforme ne corrige pas l'identité d'une école | **toujours ouvert** (UX_FIX) ; l'école corrige elle-même dans Paramètres › École & identité |
| 3 | Pas d'envoi automatique des identifiants ; changement du mot de passe à la 1re connexion non imposé | **en partie résolu** : changement imposé pour les comptes créés ou réinitialisés par l'école (D2) ; pour l'administrateur initial créé par la plateforme = OWNER_DECISION O1 ; envoi automatique toujours BLOCKED_EXTERNAL |
| 4 | Pas d'assistant de première configuration | **en partie résolu** : mise en service guidée (prochaine étape + liens) ; assistant pas à pas = E2 |
| 5 | Pas de mise hors service définitive (`DISABLED`) depuis l'Atelier Pro | **toujours ouvert** (OWNER_DECISION, hors périmètre N2) |
| 6 | Doublons d'écoles de noms proches non détectés | **toujours ouvert** (OWNER_DECISION, hors périmètre N2) |
