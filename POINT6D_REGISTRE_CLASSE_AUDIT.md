# Point 6D — Registre financier de classe

## Décisions métier verrouillées
- Une échéance financière produit une seule colonne : suppression structurelle du défaut historique de mois dupliqués.
- Le registre est construit à partir des obligations (`finance_charges`) et de leur type de frais, pas à partir du moment où l'argent a été encaissé.
- Un paiement fait à l'inscription mais destiné à juin alimente **Juin**, jamais la colonne **Inscription**.
- La colonne Inscription n'existe que si une obligation de type INSCRIPTION/REINSCRIPTION existe pour la classe/année.
- Les frais périodiques/tranches sont regroupés sous leur type de frais (ex. Frais de l'État → 1re, 2e, 3e tranche).
- Les avances explicitement ciblées sont rattachées aux vraies échéances futures via `finance_advance_targets` et apparaissent dans leur colonne cible.
- Abandon/Transfert : à compter de la date d'effet, les obligations postérieures portent le statut métier au lieu d'être présentées comme impayées. La source de vérité reste l'événement de cycle de vie et l'annulation des charges futures.
- Année, classe et devise sont des filtres explicites. PDF et Excel sont propres au sous-onglet Registre des classes.

## Architecture documentaire
PDF A3 paysage, en-têtes groupés à deux niveaux, répétition des en-têtes sur pages, identité école/année/classe/devise, note de lecture. Excel : mêmes groupes, gel, filtres, mise en page paysage et cellules financières.

## Gate local
261 tests backend PASS ; compileall PASS ; génération réelle d'un PDF et d'un XLSX échantillon PASS. Certification PostgreSQL/Windows et comparaison au golden Desktop restent à faire.
