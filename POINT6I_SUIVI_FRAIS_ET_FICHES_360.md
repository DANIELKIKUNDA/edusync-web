# Point 6I — Suivi des frais et fiches 360°

## Décision d’architecture
L’ancien concept vague **Analyses** devient **Suivi des frais**. Il s’agit d’une projection de lecture/pilotage de la même vérité financière que Recouvrement : aucune dette, aucun paiement et aucune exonération parallèle ne sont créés dans ce module.

- Encaissement : reçoit l’argent.
- Recouvrement : suit les redevables et échéances.
- Suivi des frais : pilote les familles/types de frais et permet le drill-down nominatif.
- Décisions financières : porte exonérations/réductions/prises en charge.
- Rapports : produit les documents officiels.

## Industrialisation
- Taxonomie de frais configurable par école (`fee_categories`, `fee_types.category_id`).
- Repli compatible : frais réglementaires → « Frais de l’État », autres → « Frais scolaires ».
- Vue synthétique par famille de frais : élèves concernés, net attendu, régularisé, reste, taux.
- Filtres : devise, famille de frais, frais précis, situation (en ordre / partiel / non en ordre).
- Grand tableau nominatif : élève, matricule, classe, frais, net attendu, régularisé, reste, situation.
- CDF/USD strictement séparés.
- Aucune mutation dans l’API Suivi des frais.

## Exonérations et vérité nette
`finance_charge_effective` devient la projection canonique de l’obligation nette pour les lectures concernées. Une décision ACTIVE affectée explicitement à une charge réduit son attendu. Une décision générale non affectée à une charge reste auditée mais n’est jamais ventilée silencieusement sur plusieurs frais.

Le Recouvrement et le Suivi des frais consomment cette même obligation effective afin d’éviter deux vérités concurrentes.

## Fiches modernisées
- Fiche élève : situation financière de l’année active, par frais, avec attendu/régularisé/reste.
- Fiche famille : drawer professionnel avec identité/contact, responsables, enfants et situation financière familiale détaillée par enfant/frais.
- Les fiches financières sont visibles uniquement avec le droit historique `finance.analysis.by_fee.read`.

## UX
Doctrine tables-first : contrôles compacts, cartes minimales, données centrées, tableau principal prioritaire, responsive sans sacrifier la densité métier.

## Gates
- Python compileall : PASS.
- Backend pytest : 285/285 PASS.
- Build TypeScript/React complet : non certifié dans cet environnement si les dépendances frontend ne sont pas installées.
- PostgreSQL réel, RLS et données école : certification finale à exécuter sur environnement cible.
