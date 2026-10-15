# N2 — Comparaison Desktop / Web des 13 rubriques des Paramètres

Date : 2026-10-15. Décision du propriétaire n° 8 (2026-10-14) : avant la clôture du N2, comparer les 13 rubriques du
Centre de configuration Desktop avec le Web.
Source de vérité : golden master Desktop `app/ui/settings_page.py` (EduSync École Offline 0.11.0-rc.1, lecture seule,
`C:\Users\cs-ap\dev\edusync-desktop-golden`). Côté Web : code au commit de ce rapport, sondes réelles de
`certification/n2-20261014/`.

Statuts :
- `PARITY_OK` : la règle Desktop est copiée et prouvée par une sonde réelle.
- `PARITY_GAP` : un écart Desktop reste à porter (avec le lot où il sera traité).
- `WEB_EXTENSION` : ajout propre au Web, absent du Desktop.
- `NOT_APPLICABLE_IN_SAAS` : propre à un logiciel installé dans l'école ; sans objet dans un service en ligne (décision du propriétaire).

## 1. Synthèse

| # | Rubrique Desktop | Statut | Preuve Web | Écart restant |
|---|------------------|--------|------------|---------------|
| 1 | Mise en service | `PARITY_OK` (+ `PARITY_GAP` mineur) | liste de préparation guidée (prochaine étape + liens), n2_probe | assistant pas à pas (E2), affichage « prochain élève / prochaine famille » de la numérotation automatique |
| 2 | Identité | `PARITY_OK` (+ `PARITY_GAP` mineur) | nom, contacts, adresse, ville, province, logo ; n2_probe | champ « devise / mention » (`motto`) absent |
| 3 | Années scolaires | `PARITY_OK` (+ `PARITY_GAP` mineur) | préparer, activer, clôturer, archiver ; année close en lecture seule | « reprendre depuis l'année précédente » (confort, écart E3) |
| 4 | Structure & classes | `PARITY_OK` | sections, options avec groupe d'Humanités (liste fermée GENERAL / TECHNICAL / OTHER), états ACTIVE / INACTIVE / ARCHIVED, droit d'état séparé du renommage ; class_status_probe 21/21 | création de plusieurs classes en une fois (confort) |
| 5 | Types de frais | `PARITY_OK` | catalogue, périodicité, frais réglementaire | modèles de frais préremplis (confort) |
| 6 | Tarifs & barèmes | `PARITY_OK` | règles datées école → section → groupe d'Humanités → classe académique → classe ouverte (priorités 100/200/350/500/600), statuts ACTIVE / PENDING_OFFICIAL / INACTIVE, mois de facturation, mois exigé à l'inscription, « appliquer aux classes ouvertes », échéances et frais dus ; tariff_rules_probe 36/36, fee_schedules_probe 18/18 | — |
| 7 | Conditions d'inscription | `PARITY_OK` + `WEB_EXTENSION` | obligations annuelles (frais lié, obligatoire, moment, différé, regroupement, portée, ordre), activation, validation de la rubrique ; admission_probe 16/16. Extension Web : « règles de saisie à l'inscription » (champs exigés) | — |
| 8 | Avantages & cas particuliers | `PARITY_OK` | politiques par année (famille nombreuse, enfants du personnel), plafonds, gratuits, réduction sur le frais, cumul interdit, désignation manuelle à l'inscription ; benefits_probe 21/21 | — |
| 9 | Règles d'encaissement + Plans de paiement anticipé | `PARITY_OK` (+ `PARITY_GAP` N3) | acomptes, minimum, mois futurs, modes acceptés, mode et référence enregistrés (payment_policy_probe 18/18) ; plans anticipés copiés du Desktop (anticipation_probe 30/30, anticipation_ui_check PASS) | présentation des acomptes dans les rapports (stockée, branchée aux rapports en N3) ; **fonds anticipé** (réception libre, imputation, remboursement, interrupteur « paiements anticipés ») à porter comme mécanisme distinct |
| 10 | Contributions en nature | `PARITY_OK` (catalogue) | catalogue des contributions, certifié au N1 (non resondé en N2) ; aucune transformation en paiement | suivi des remises : module terrain (N3) |
| 11 | Articles scolaires | `PARITY_OK` (catalogue) + `PARITY_GAP` N3 | catalogue, prix, stock (certifié au N1), vente à la caisse dans la séquence unique de reçus | mode de vente Desktop à comparer en N3 Finance |
| 12 | Documents & numérotation + Sauvegarde & restauration | Documents : `PARITY_OK` (+ `PARITY_GAP` N3) ; Sauvegarde : `NOT_APPLICABLE_IN_SAAS` | reçus PRÉFIXE-ANNÉE-000123, copies 1 à 5, formats A5 / 80 mm / 58 mm, politique d'impression ; receipt_settings_probe 12/12 | préfixe des rapports (avec les rapports numérotés, N3) ; signataire et affichage du logo : stockés au Desktop mais lus par aucun document (non portés) ; dossier des documents et imprimantes : poste local, sans objet. Sauvegarde : responsabilité de la plateforme, aucune restauration directe par l'école (décision n° 2) |
| 13 | Assistance technique | `NOT_APPLICABLE_IN_SAAS` | diagnostics, santé et sauvegardes dans l'Atelier Pro (plateforme) | export du diagnostic par l'école : sans objet (l'assistance a l'accès plateforme, tracé) |

Hors rubriques Desktop : politique `COMMUNICATIONS` (SMS) = `WEB_EXTENSION` (décision n° 7, ne bloque pas le N2).

## 2. Détail des écarts restants

| Écart | Rubrique | Type | Traitement |
|-------|----------|------|-----------|
| Fonds anticipé (advance_funds : réception, imputation, remboursement, reçu propre, droits `finance.advance_funds.*`, interrupteur `advance_payments_enabled`) | 9 | `PARITY_GAP` Finance | N3 Finance, mécanisme séparé, jamais fusionné avec les plans (doctrine L6) |
| Présentation des acomptes dans les rapports (`partial_reporting_mode`) | 9 | `PARITY_GAP` Finance | N3, avec les rapports de recouvrement |
| Préfixe des rapports | 12 | `PARITY_GAP` Finance | N3, avec les rapports numérotés |
| Chaîne séquentielle des mensualités : le Desktop impose l'ordre sur SCOLARITE ; à recomparer finement | 6 / 9 | `PARITY_GAP` à vérifier | N3 Finance (comparaison de la caisse) |
| Mode de vente des articles | 11 | `PARITY_GAP` à vérifier | N3 Finance |
| Devise / mention de l'école | 2 | `PARITY_GAP` mineur | N3 (documents officiels) |
| Assistant pas à pas, reprise de l'année précédente, création de classes en lot, modèles de frais, affichage de la prochaine numérotation | 1, 3, 4, 5 | `PARITY_GAP` confort | backlog UX ; aucune règle financière en jeu |

Aucun écart restant ne touche une règle dont la Finance dépend pour le N3, à part ceux qui sont classés N3 Finance
ci-dessus : ils seront portés dans ce lot.

## 3. Ce qui a changé depuis l'audit

Lots de parité L1 à L7 (commits `106d02d` à `9064067`) : tarifs hiérarchiques et groupes d'Humanités, échéances et frais
dus, avantages, conditions d'admission, règles d'encaissement, plans anticipés, reçus. Corrections O2 / O6 (états de
classe, droit d'état séparé du renommage) et O1 (le premier administrateur choisit son mot de passe).

## 4. Décisions du propriétaire encore ouvertes

1. Rôle titulaire de `finance.anticipation_plans.manage` (aucun rôle standard ; au Desktop : ADMIN et DIRECTION).
2. Transfert financier lors d'un changement de classe : le Web copie le Desktop (refus dès qu'un frais existe) ; à
   confirmer si une autre règle est voulue.
