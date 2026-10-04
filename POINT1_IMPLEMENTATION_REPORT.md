# Point 1 — Rapport d'implémentation

Le Point 1 ne porte aucun module métier Desktop. Il verrouille la fondation sur laquelle les points 2→11 seront exécutés.

## Changements réalisés

- ajout d'une classification codée des opérations offline;
- ajout d'invariants d'architecture testables;
- doctrine Finance mise à jour : single-writer WEB-0D = transitoire, cible = multi-caissier autorisé;
- création de quatre ADR de référence;
- matrice offline officielle;
- gate de fermeture du Point 1;
- aucune décision finale de rôles/permissions (réservée au Point 3).

## Règle de non-régression

Tout point futur peut enrichir l'implémentation, mais ne peut pas : supprimer l'isolation école, rendre Redis autoritatif, revenir au last-write-wins financier, supprimer l'idempotence, fusionner silencieusement des conflits financiers, ou bloquer globalement les opérations quotidiennes simplement parce qu'Internet est indisponible.
