# Point 6B — Autres encaissements / dettes antérieures / ventes d’articles

## Décisions métier verrouillées
- Le libellé **Outils spécialisés** est retiré du guichet au profit de **Autres encaissements**.
- Le paiement anticipé n’est pas dupliqué ici : il reste intégré à Encaissement rapide.
- Une dette d’une année clôturée/archivée conserve son année d’origine lors de son règlement. Le caissier n’a pas à changer l’année scolaire globale.
- La recherche d’encaissement devient transannuelle : un ancien élève ou un élève actif avec dette historique reste retrouvable.
- La vue **Dettes antérieures** est une vue de consultation/contrôle ; le guichet rapide signale également les dettes historiques et permet d’ouvrir l’inscription d’origine.
- **Vente d’articles** est un parcours de caisse ; la gestion du stock appartient à l’Intendance.
- Le code/référence d’article vient du catalogue et n’est jamais une saisie quotidienne du caissier.

## Stock
Migration additive `0018_finance_other_collections_inventory.sql` : stock courant, mouvements append-only et ventes. Une vente d’article suivi verrouille le stock (`FOR UPDATE`), refuse le stock insuffisant, crée paiement + vente + sortie de stock dans la même transaction et conserve l’idempotence du paiement.

## UX
Trois entrées compréhensibles sous Encaissement : **Encaissement rapide**, **Autres encaissements**, **Dettes antérieures**. Le caissier recherche l’élève/famille avec le même moteur, choisit l’article, la quantité et encaisse. Aucun champ Référence manuel.

## Validation locale
- Python compileall : PASS
- Pytest : 249/249 PASS
- Build frontend complet : gate Windows/Node restant si dépendances npm absentes.
- PostgreSQL réel + concurrence multi-caissier + inventaire réel : gate de certification finale.
