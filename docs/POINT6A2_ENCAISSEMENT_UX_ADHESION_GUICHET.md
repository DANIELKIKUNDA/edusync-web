# Point 6A.2 — Encaissement maximal : adhésion au guichet

## Doctrine verrouillée
- Le plan anticipé est configuré une fois par l'école pour l'année et la devise concernées.
- Il est **disponible au guichet sans préinscription individuelle**.
- L'adhésion d'un enfant peut être constatée lors de son premier paiement avec avance.
- Le choix est mémorisé par `enrollment_id`; il n'est jamais imposé automatiquement aux frères/sœurs.
- Un refus antérieur ne rend pas le plan définitivement indisponible : le parent peut changer d'avis à un paiement ultérieur tant que le plan école reste actif.
- Le tarif normal reste intact. L'avance est une allocation distincte, jamais une hausse du tarif.
- L'utilisateur ne quitte jamais Encaissement rapide pour enregistrer l'avance.

## UX guichet
Parcours courant : **Rechercher → Élève → Frais → Montant → Encaisser**.

Quand un plan est disponible, deux choix simples sont montrés :
1. **Paiement normal** — règle seulement les obligations sélectionnées.
2. **Paiement avec avance** — le surplus est affecté aux échéances futures.

Au premier paiement avec avance, une confirmation unique affiche la ventilation `frais / avance / total reçu`. Après confirmation, l'adhésion est créée dans la même transaction que le paiement. Les passages suivants indiquent simplement que la participation est déjà mémorisée.

Le module Fonds anticipés reste un outil de suivi/contrôle/rapport, pas un deuxième guichet obligatoire.
