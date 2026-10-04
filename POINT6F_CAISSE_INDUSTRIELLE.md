# Point 6F — Caisse industrielle multi-caissier

## Décision métier
La caisse ne s'ouvre jamais silencieusement à la réception d'un paiement. Chaque caissier possède une session personnelle explicite. Si aucune session n'est ouverte, l'encaissement reste fail-closed; l'UX propose une ouverture en un clic avec fond initial CDF/USD. Cela conserve la rapidité au guichet tout en donnant une frontière d'audit fiable.

## Industrialisation
- correction du schéma historique qui empêchait plusieurs sessions CLOSED par caissier;
- une seule session OPEN par école + membership via index partiel;
- date métier, fond initial CDF/USD, comptage réel à la clôture, écart calculé;
- journal unifié encaissements/dépenses;
- événements append-only OPEN/CLOSE/REOPEN/EXPENSE;
- historique par date; lecture des autres caisses uniquement avec `finance.cash.other.read`;
- CDF et USD strictement séparés;
- UI moderne: état OUVERTE/FERMÉE, KPIs, ouverture, clôture, calendrier, historique, journal;
- aucun pictogramme X/II technique dans le nouveau parcours; libellés métier explicites.

## Multi-caissier
Une caisse appartient à un membership. Deux caissiers peuvent avoir chacun une caisse OPEN simultanément. Les paiements restent rattachés à la session qui les a encaissés. Le responsable autorisé peut consulter les autres caisses sans fusionner leurs responsabilités.

## Gate local
- `python -m compileall backend/src`: PASS
- `pytest`: 269/269 PASS
- build React complet: non exécuté (dépendances frontend absentes du checkpoint)
- PostgreSQL réel, concurrence multi-caissier, Windows/browser et impression du journal: gates finaux.
