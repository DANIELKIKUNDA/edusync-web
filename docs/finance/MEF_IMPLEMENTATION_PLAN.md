# Politique annuelle d'exigibilité

Statut : **implémentée et fusionnée** (PR #33, version 1.0.0-rc.2, 01/11/2026) — migration `0105_finance_annual_exigibility`,
moteur de calcul, génération des charges, recouvrement, API et interface (Paramètres › Tarifs), certifiée sur PostgreSQL
réel dans la CI (`tools/ci/mef_postgres_integration.py`). Les étapes ci-dessous décrivent la conception d'origine.

Une politique est définie par école et année scolaire, avec règles par type de frais et seuils calendaires paramétrables. Les mois antérieurs à l'inscription peuvent être non exigibles, exigibles ou soumis à une règle spécifique. Les exonérations individuelles restent distinctes de l'absence d'obligation. Toute modification de politique est versionnée et auditée.

Étapes : migrations, moteur de calcul, intégration génération des charges, recouvrement, API et interface, tests PostgreSQL et navigateur. Aucune fusion sans certification.
