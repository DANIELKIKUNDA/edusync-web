# ADR-004 — Finance offline : CASH autorisé et cible multi-caissier

**Décision : acceptée et verrouillée.**

Le CASH peut être encaissé de façon définitive hors connexion si l'appareil a reçu une autorité financière bornée. WEB-0D single-writer est une étape transitoire. La cible du point 2 est un protocole multi-caissier qui conserve exact-once, reçus uniques, audit, plafonds/autorités bornées, caisse par appareil, CDF/USD séparés et réconciliation serveur.

Aucune fusion automatique d'écritures financières contradictoires n'est permise.
