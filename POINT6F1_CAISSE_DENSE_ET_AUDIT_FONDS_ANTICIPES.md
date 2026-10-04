# Point 6F.1 — Caisse dense + audit Fonds anticipés

## Caisse
- « Ma caisse » reste la responsabilité physique individuelle du caissier.
- Entrées, sorties et solde théorique sont calculés par session et par devise.
- La « Situation globale des caisses » est une agrégation de contrôle, jamais une caisse physique supplémentaire.
- Elle exige `finance.cash.other.read` et reste invisible au caissier non autorisé.
- CDF et USD restent strictement séparés.
- UX volontairement dense : tableaux prioritaires, bandeaux et contrôles compacts, pas de mur de cartes KPI.

## Fonds anticipés — décision d'audit
Le guichet d'encaissement anticipé ne doit PAS redevenir un onglet autonome du Centre financier : le paiement avec avance est déjà intégré à Encaissement rapide, avec adhésion possible au premier paiement et ventilation explicite.

Le domaine « Fonds anticipés » reste cependant nécessaire en backend et en contrôle, car il porte des responsabilités distinctes de l'encaissement :
- consultation des avances non encore imputées ;
- imputation/consommation vers les échéances cibles ;
- remboursement exceptionnel d'un solde non imputé, audité ;
- historique et justification ;
- rapports/PDF/XLSX préservés du Desktop ;
- analyse financière.

Décision UI : ne pas ajouter « Fonds anticipés » parmi les onglets quotidiens du caissier. La configuration des plans relève des Paramètres/gestion autorisée. Le suivi des avances sera une vue de contrôle compacte accessible uniquement aux rôles disposant des capacités `finance.advance_funds.*` / `finance.analysis.advance.read`, à industrialiser avec le bloc de contrôle financier. Cela évite un second guichet et les doubles saisies.
