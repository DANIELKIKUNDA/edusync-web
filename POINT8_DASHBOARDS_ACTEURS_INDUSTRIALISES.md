# Point 8 — Dashboards acteurs industrialisés

## Doctrine
Un dashboard est une surface de décision, jamais une seconde implémentation métier. Les données proviennent des read-models Effectifs, Recouvrement, Suivi des frais et Caisse déjà présents. L'affichage est dérivé des permissions effectives, pas d'un intitulé décoratif de poste.

## Modèles branchés
- Direction / Gouvernance : effectifs institutionnels, abandons/sorties, recouvrement, familles de frais, alertes/mouvements.
- Direction scolaire : Préfet des études, Directeur des études, Directeur de discipline et direction de section. Priorité scolarité/effectifs/mouvements; recouvrement secondaire seulement si permission accordée. Les rôles secondaires restent limités à SECTION=SECONDAIRE par le garde RBAC existant.
- Responsable financier : recouvrement et familles de frais, sans transformer le rôle en caissier.
- Caissier : état de sa caisse, entrées/sorties/solde théorique, accès encaissement, repère d'effectif école et recouvrement secondaire.
- Secrétariat : socle administration scolaire selon permissions.
- Intendance : contrat de cockpit reconnu, mais aucune métrique stock/local/patrimoine n'est inventée avant le Point 9.

## Correction transversale importante
Le suivi mensuel de recouvrement accepte maintenant les scopes effectifs du capability grant et filtre SQL par SECTION/CYCLE ou CLASS. Un Préfet/Directeur secondaire ne reçoit donc pas silencieusement le recouvrement de toute l'école lorsque son rôle est limité à SECONDAIRE.

## UX
Accueil devient le module par défaut. Cockpit compact, tables-first, peu de cartes, drill-down vers les modules propriétaires, responsive et sans personnages décoratifs.

## Validation locale
- pytest : 297/297 PASS
- Python compileall : PASS
- build React/TypeScript complet : non certifié dans cet environnement (node_modules absent)
- PostgreSQL réel / Windows / navigateur : validation finale requise sur l'environnement cible
