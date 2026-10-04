# EduSync — Point 6A — Encaissement industriel
Date: 2026-09-13

## Audit / décision
Le Desktop reste l'oracle métier. Les preuves d'audit disponibles établissent une certification finance 29/29 et les capacités checkout existantes, mais l'archive source Desktop brute n'est pas matérialisée dans ce checkpoint. Aucun bouton historique n'est donc supprimé sans preuve.

## Porté maintenant
- Centre financier réellement navigable selon permissions.
- Encaissement rapide : recherche globale élève/famille/matricule/téléphone, debounce 180 ms.
- Sélection élève puis lecture immédiate charges/payé/reste.
- Frais ponctuels et mensualités visibles; mensualités futures verrouillées jusqu'au solde de la première due.
- « Mensualité suivante » = première mensualité admissible.
- « Ajouter un enfant » charge les enfants du même family_id.
- « Effacer » remet le poste d'encaissement à zéro sans mutation métier.
- CDF/USD strictement séparés.
- Total automatique sur le reste réel.
- Encaissement protégé par permission + caisse personnelle ouverte + Idempotency-Key + verrou FOR UPDATE.
- Paiement et impression du reçu séparés. Aucun print automatique.
- RLS forcée sur les nouvelles tables financières.

## Admission
Admission n'est pas inventée automatiquement. Si l'école configure un frais Admission et qu'une charge ACTIVE existe, elle apparaît comme frais ponctuel normal. Sans décision/tarif/charge, aucune dette Admission n'est créée.

## Gate
CANDIDAT LOCAL POINT 6A. Les invariants purs et non-régressions sont testés. La certification PostgreSQL live, Windows navigateur et concurrence réelle multi-caissier reste au gate final machine.
