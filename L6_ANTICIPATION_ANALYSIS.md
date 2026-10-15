# L6 — Plans de paiement anticipé : qualification du mécanisme Web avant migration

Date : 2026-10-14. Décision du propriétaire : parité Desktop, avec la doctrine **Plan anticipé ≠ Fonds anticipé**.

## 1. Les deux concepts du golden master Desktop

| | Plan de paiement anticipé | Fonds anticipé |
|---|---|---|
| Source | `app/db/anticipation.py`, `schema.sql` (anticipation_plans, _memberships, _installments, _payment_links) | `app/db/operations.py` (receive / allocate / reverse_advance_fund), `schema.sql` (advance_funds, advance_allocations, advance_receipts) |
| Nature | **allocation dirigée** d'un paiement vers des charges futures identifiées | **provision reçue avant imputation** |
| Argent | va directement sur les frais (mois courant, puis seulement les mois cibles du plan) ; aucune réserve | conservé comme montant disponible, imputé plus tard, remboursable s'il n'est pas imputé |
| Paramétrage | plan : portée (école, section, groupe d'Humanités, classe académique, classe), frais mensuel, mois cibles, mois de contribution, répartition égale, adhésion facultative ou obligatoire, date d'effet | aucun plan : réception libre (mode, référence, reçu propre) |
| Droits du registre | `finance.anticipation_plans.manage/read`, `finance.anticipation_membership.set`, `finance.anticipation.collect` | `finance.advance_funds.receive/allocate/refund/read/receipt.print` |
| Interrupteur de la politique d'encaissement | — (paiement autorisé par le plan, sans contrôle d'acompte ni de mois futur) | `advance_payments_enabled` |

## 2. Ce qu'est le mécanisme Web actuel (point 6A.1 / 6F.1)

Tables `finance_anticipation_plans` (libellé, devise, `rules_json` libre), `finance_anticipation_memberships` (ACCEPTED / DECLINED),
`finance_advance_allocations` (montant, **restant à imputer**, résumé de cible), `finance_advance_targets` (fléchage vers des charges).

À la caisse (`collect(use_anticipation=True)`) : la part « normale » paie les frais sélectionnés ; le **surplus** est enregistré dans
`finance_advance_allocations` (provision), fléché vers des mois cibles lus dans `rules_json`, **sans être imputé aux frais**
(`paid_amount` n'augmente pas). Ce surplus n'est accepté que si un « plan » a été accepté pour l'inscription.

**Qualification** : c'est une **implémentation simplifiée du plan anticipé** (adhésion par inscription, mois cibles du plan,
surplus autorisé seulement par le plan) **réalisée avec un stockage de type fonds** (provision non imputée). Ce n'est pas un
fonds anticipé libre au sens Desktop : il n'existe ni réception autonome, ni imputation, ni remboursement, ni reçu propre ;
la provision ne peut naître que d'un plan.

Données : **0 plan, 0 adhésion, 0 avance** dans la base de démonstration et dans la base vierge (vérifié le 2026-10-14).

## 3. Décision technique appliquée (sans redéfinir le métier)

1. **Plans anticipés** : portage du modèle Desktop à l'identique (nouvelles tables, création dans les Paramètres, adhésion,
   échéancier, encaissement « mois courant puis mois cibles », liens d'allocation, achèvement).
2. **Ancien chemin Web** (`use_anticipation`) : retiré de la caisse après la migration — l'écran Desktop ne doit pas cohabiter
   avec une imputation différente. Les tables sont **conservées telles quelles** (aucune suppression ; aucune donnée à migrer).
3. **Fonds anticipé** : concept distinct, **non fusionné**. Le Desktop le porte par `advance_funds` ; le Web n'en a pas
   d'équivalent complet. Il reste à porter comme mécanisme séparé (`finance.advance_funds.*`, interrupteur
   `advance_payments_enabled`) : écart consigné (`PARITY_GAP`), hors du lot L6 « plans ».
4. **Droit de création des plans** : `finance.anticipation_plans.manage` n'est attribué à aucun rôle standard par les décisions
   de rôles du propriétaire (point 3B). Au Desktop : administrateur et direction. → `OWNER_DECISION_REQUIRED` (quel rôle).
