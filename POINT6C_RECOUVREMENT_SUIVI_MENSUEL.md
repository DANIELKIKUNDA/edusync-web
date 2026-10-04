# Point 6C — Recouvrement / Suivi mensuel

## Décisions verrouillées
- Suivi mensuel dépend de l'année scolaire sélectionnée et de la devise.
- Redevables / En ordre / Non en ordre sont des états mensuels et ne sont jamais additionnés dans le Total général.
- Total général = somme Attendu, Encaissé caisse, Régularisé hors caisse, Régularisé total, Reste; taux global = régularisé total / attendu.
- Les obligations annulées ne gonflent jamais l'attendu. Les abandons/transferts doivent donc produire/corriger les obligations nettes en amont; le read-model consomme uniquement les charges ACTIVE.
- Chaque sous-onglet de Recouvrement possède ses propres actions d'export. Le suivi mensuel dispose désormais de PDF + Excel dédiés.
- Les exports sont enrichis: identité école, titre, année, devise, en-têtes lisibles, ligne Total général, mise en page impression.
- Aucun nouveau droit global fictif: lecture = finance.recovery.monthly.read; export mensuel réutilise provisoirement les droits documentaires VF-01 existants jusqu'à décision RBAC dédiée.

## Limite volontaire
Le présent lot ferme uniquement Suivi mensuel. Registre des classes et synthèses restent visibles comme prochaine séquence mais non industrialisés ici.
