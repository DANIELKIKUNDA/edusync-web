# Paramètres École — comparaison desktop (edusync-desktop-golden) ↔ web, onglet par onglet (24/10/2026)

Source desktop : `app/ui/settings_page.py` (13 rubriques), `app/ui/configuration_wizard.py` (assistant en 7 étapes),
`app/db/configuration.py` (référentiel RDC, `configure_regulatory_fee_bundle`). Principe repris : **l’utilisateur ne
saisit jamais un code interne**.

> Correction honnête : la première passe (PR #11) annonçait une parité trop large. Le propriétaire a relevé
> l’absence d’assistant tarifaire, des parallèles imposées à tous les niveaux et des avantages limités à un seul
> frais. La passe 2 ci-dessous les traite ; la colonne « Reste à faire » liste ce qui n’est **pas** encore porté.

| Rubrique | Desktop | Web — passe 1 (PR #11) | Web — passe 2 (cette branche) | Reste à faire |
|---|---|---|---|---|
| Vue d’ensemble | Assistant intelligent, progression, prochain matricule | Assistant de mise en service + parcours | Assistant : **niveaux à cocher et parallèles par niveau** (repart des classes déjà ouvertes) | Prochain matricule (pas d’API) ; étape « tarifs » dans l’assistant de mise en service (l’assistant tarifaire est dans l’onglet Tarifs) |
| École & identité | Nom, contacts, adresse, devise / mention, logo | Enregistrement réparé (0086), logo, erreurs expliquées | — | « Devise / mention » (nouvelle colonne à décider) |
| Années scolaires | Créer, reprendre, activer, clôturer, archiver | Code généré | — | — |
| Structure & classes | Options en Humanités seulement, lot de classes, parallèles | Lot de classes, **même nombre de parallèles pour tous les niveaux** | **Parallèles choisies niveau par niveau** (et option par option en Humanités) : ex. 2 en 1re, 2e, 3e primaire, 1 ailleurs. Une classe sans lettre compte comme la première ; un niveau déjà en A/B ne reçoit jamais de classe sans lettre | — |
| Types de frais | 11 modèles + personnalisé, modification depuis la ligne | Modèles + frais personnalisé | **Modifier** (nom, périodicité, devise, réglementaire) et **désactiver / réactiver** un frais depuis sa ligne | — |
| Tarifs & barèmes | « Assistant de création du tarif » avec conseiller, « Configurer les frais réglementaires », mois, appliquer | Formulaire de règle unique, mois, appliquer | **Assistant tarifaire** : (1) grille école / section / niveau / groupe d’Humanités en un écran, ligne « en attente du barème officiel » ; (2) règle sur **plusieurs cibles** avec conseiller (« s’appliquera à N classes, M gardent une règle plus précise ») ; (3) **frais réglementaires** du desktop (État 12 000 / 21 000 / 23 000 / 25 000 CDF par tranche, TENASOSP 60 000 en 8e EB, frais techniques 25 000) modifiables avant enregistrement, frais manquants créés. **Aperçu du montant de chaque classe** avant d’enregistrer | Capacité serveur dédiée `settings.regulatory_fees.configure` toujours PLANNED : l’assistant utilise les droits existants (types de frais + tarifs), même audit par règle |
| Inscriptions | Conditions d’admission | Présent | — | — |
| Avantages | Famille nombreuse, enfants du personnel (un frais) | Un seul frais par avantage | **Plusieurs frais par avantage** (migration 0087 : liste figée sur le bénéficiaire, ancienne colonne conservée) ; lien vers les exonérations individuelles | — |
| Exonérations individuelles | Décisions financières | Décision sur un frais, **code à taper** | **Plusieurs frais ou plusieurs échéances cochés** (une décision traçable par frais), pour tout élève, sans être enfant du personnel ni pris en charge | — |
| Encaissement | Acomptes, modes, fonds et plans anticipés | Présent | — | — |
| Contributions / Articles | Modèles, codes générés | Modèles, codes générés | — | — |
| Documents & sauvegardes | Préfixes, copies, signataire, sauvegarde / restauration | Lien vers Documents | — | Préfixes / signataire / copies côté web ; sauvegarde à la demande (capacités PLANNED) |
| Assistance technique | Export du diagnostic | — | — | Capacités `settings.diagnostics.*` PLANNED |

## Ce qu’EduSync web fait de plus que le desktop

- aperçu, avant enregistrement, du montant que **chaque classe ouverte** paiera, selon la même priorité que le serveur ;
- une règle tarifaire pour **plusieurs cibles** d’un coup ;
- parallèles **par option** des Humanités, pas seulement par niveau ;
- un avantage couvrant **plusieurs frais** ; des exonérations individuelles sur plusieurs frais en une fois ;
- toutes les erreurs expliquées en français, en indiquant la ligne en cause et ce qui a déjà été enregistré.

## Preuve « vrai administrateur » (stack locale, école C)

`frontend/browser-tests/local_settings_parity2.mjs`, vrai navigateur, vrai serveur, vraie base : **14 étapes sur 14
réussies au premier passage**. La grille part des parallèles existantes ; ajouter seulement une 4e primaire C ;
« tout à 1 » ne crée rien ; modifier, désactiver et réactiver un frais ; grille tarifaire avec un montant particulier
pour la 6e primaire, vérifié dans l’aperçu ; une règle pour 7e et 8e EB ; frais réglementaires ; règles visibles ;
barèmes appliqués ; avantage « enfants du personnel » sur deux frais, toujours coché après rechargement.
Affichage mobile (390 px) vérifié, sans défilement horizontal.

Non prouvé en navigateur dans cette passe : la décision d’exonération sur plusieurs frais (l’école de test n’a pas
d’élève inscrit). Elle est couverte par la vérification des types et par le test du modèle de lecture côté serveur.
