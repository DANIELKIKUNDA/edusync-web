# Contrat de préservation — Desktop → Web

WEB-0A interdit toute simplification silencieuse des modules Desktop déjà certifiés.

Avant de porter un module métier :

1. inventorier écrans, actions, filtres, permissions et états vides ;
2. inventorier tables / invariants / dates métier ;
3. figer les scénarios Desktop comme golden scenarios ;
4. figer PDF/Excel comme golden masters ;
5. migrer les fixtures SQLite vers PostgreSQL ;
6. comparer sorties, totaux et états ;
7. ajouter `school_id`, RBAC, audit, notifications/offline selon politique ;
8. certifier la parité avant fermeture du portage.

## Priorité de préservation

- Paramètres : TRÈS FORTE
- Personnel : FORTE
- Élèves / inscriptions / familles : TRÈS FORTE
- Effectifs & dépôts : FORTE
- Finance / Caisse : MAXIMALE
- Documents / exports : MAXIMALE
- Imports : données MAXIMALES, UX enrichissable

## Exports

Les générateurs Python existants sont des actifs du produit. Ils seront d'abord encapsulés derrière `DocumentGeneratorPort`; une réécriture n'est autorisée qu'avec preuve de parité.
