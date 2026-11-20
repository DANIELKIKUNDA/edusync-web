# Certification mobile globale et périmètres — 20 novembre 2026

## Décision de livraison

Ne pas fusionner la passe mobile tant que la matrice ci-dessous n'est pas entièrement verte sur une vraie pile locale
ou en staging. Une compilation réussie ne remplace pas l'observation visuelle sur téléphone.

## Règles métier non négociables

- Un préfet affecté au secondaire ne reçoit que les élèves, classes, effectifs, agents, communications et options de
  filtre du secondaire.
- Un directeur ou une directrice de section ne reçoit que ses sections affectées.
- Un périmètre supplémentaire n'est visible qu'après une affectation explicite.
- Les listes, compteurs, exports, recherches, suggestions et sélecteurs obéissent au même périmètre.
- Les routes sans périmètre valide échouent fermées : elles ne reviennent jamais silencieusement à toute l'école.
- Importation : aucun accès pour préfet, directions ou autres rôles sans permission explicite d'import.

## Matrice mobile à certifier page par page

| Module | Pages et parcours minimum | Contrôles téléphone |
|---|---|---|
| Finance | Encaissement, caisse, journal, supervision, suivi financier, recouvrement, décisions/exemptions, responsabilités, crédits, rapports administration, rapports direction, historique imports | Filtres verticaux, cartes lisibles, total/action accessibles au pouce, recherche et résultats au-dessus du clavier, aucun débordement |
| Élèves et inscriptions | Vue d'ensemble, répertoire élèves, familles, nouvelle inscription, réinscription, dossier élève, import si autorisé | Classe/section limitées au rôle, recherche visible avec clavier, formulaire en une colonne, actions finales collantes, cartes au lieu du tableau PC |
| Effectifs | Synthèse, sections, classes, options, registres et exports | Compteurs et listes du même périmètre, filtres pleine largeur, actions tactiles, aucun primaire pour le préfet secondaire |
| Personnel | Répertoire, fiche agent, affectations, présence/statut, synthèse | Agents et affectations limités au périmètre, filtres empilés, fiche plein écran, actions ≥ 44 px |
| Intendance | Tableau de bord, articles, stock, mouvements, anciens soldes/outils | Résumé avant détail, registres navigables, formulaires et actions utilisables à une main |
| Documents | Liste, recherche, aperçu PDF, téléchargement/impression | Aperçu prioritaire, boutons visibles, aucune largeur fixe, fermeture accessible |
| Communication | Centre, destinataires, aperçu, envoi, historique | Destinataires limités au périmètre, filtres et composer mobiles, modal fermable, textes français |
| Synchronisation | État, file d'attente, conflits, relance | Cartes compactes, statuts lisibles, actions non coupées, fonctionnement hors ligne observé |
| Paramètres | Toutes rubriques accessibles au rôle | Navigation horizontale maîtrisée, formulaires en une colonne, pied d'action collant, aucune permission supplémentaire |
| Accueil et navigation | Tableau de bord, cloche, profil, menu Plus, changement d'année | Une seule identité de page, barre basse stable, aucun module interdit, badges et feuilles mobiles corrects |

## Tailles obligatoires

Tester au minimum 320×568, 360×800, 390×844, 412×915 et 768×1024, en portrait. Faire aussi un contrôle rapide
en paysage à 844×390. La largeur 390 seule n'est pas une certification globale.

## Comptes obligatoires

Administrateur, gestionnaire, caissier, secrétariat, intendant, préfet secondaire, directeur des études, directeur de
discipline, direction primaire, direction maternelle, responsable financier et promoteur.

Pour le préfet, conserver deux scénarios distincts :

1. secondaire uniquement ;
2. secondaire plus un périmètre additionnel explicitement attribué.

## Commandes de contrôle local

```bash
cd backend
PYTHONPATH=src python -m pytest -q \
  tests/test_secondary_leadership_backend_regression.py \
  tests/test_section_leadership_personnel_scope_sql.py \
  tests/test_section_leadership_personnel_http.py \
  tests/test_section_leadership_schooling_parity_fail_closed.py \
  tests/test_operational_structure_scope.py

cd ../frontend
npm test -- --run
npm run build
node browser-tests/local_mobile_audit.mjs
```

Le robot produit `.local/mobile_audit/audit.json` et une capture par rôle et module. Toute valeur `overflow > 0`, tout
tableau coupé, toute cible trop petite, toute erreur de module ou tout module interdit bloque la fusion.

## Contrôle manuel du clavier

Sur Finance, Élèves, Personnel et Communication : toucher la recherche, saisir au moins trois lettres, puis vérifier
que le champ actif remonte dans la zone visible et que les premières suggestions restent au-dessus du clavier. Répéter
avec un champ situé en bas d'un formulaire d'inscription.

## Résultats déjà acquis sur cette branche

- 62 tests ciblés de périmètre serveur réussis.
- 145 tests frontend réussis.
- Build frontend de production réussi.
- Finance réorganisée page par page sur la branche de passe mobile.
- Recentrage automatique du champ actif lors de l'ouverture/redimensionnement du clavier ajouté globalement.

## Blocage de cet environnement

Le navigateur Playwright ne peut pas démarrer ici à cause d'une interdiction noyau sur la création de socket ; le
téléchargement du navigateur est également refusé par le CDN. Claude/local doit donc exécuter la matrice visuelle,
corriger chaque écart observé, joindre `audit.json` et les captures, puis seulement fusionner.
