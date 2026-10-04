# Point 10H8 — Pagination transversale

Pagination serveur durcie sur les grands registres restants : Audit, historique Personnel et listes principales d’Intendance. Les annuaires Élèves/Familles et registres Effectifs/Dépôts conservent leur pagination existante. Les exports documentaires restent hors pagination écran et portent sur le périmètre filtré complet.

Doctrine : offset borné pour annuaires administratifs ; curseur à privilégier lors de la certification live pour journaux append-only très profonds (audit, mouvements, outbox). Aucun changement des règles métier ou des golden masters documentaires.
