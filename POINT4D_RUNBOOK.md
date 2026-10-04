# Point 4D — Runbook de validation finale

1. Appliquer les migrations jusqu'à `0015_effectifs_depots_domain.sql` sur une base de recette PostgreSQL.
2. Charger une école DEMO avec Maternelle, Primaire et Secondaire, plusieurs classes et mouvements annuels.
3. Vérifier successivement Toute l'école, Maternelle, Primaire, Secondaire : KPI et grille doivent changer ensemble.
4. Pour `Par classe`, vérifier les 14 colonnes : Section, Classe, puis F/G/T pour Inscrits, Abandons, Transférés, Élèves actifs.
5. Contrôler la ligne Total général.
6. Tester les mouvements : recherche, type, classe, pagination et état vide.
7. Vérifier qu'un chef de section ne lit jamais hors de son scope.
8. Tester un dépôt dans l'année ACTIVE ; tenter le même dans CLOSED et vérifier le refus.
9. Vérifier que le registre Dépôts suit exactement le périmètre actif.
10. Ouvrir PDF et Excel ; contrôler identité/logo, périmètre, données, total et lisibilité.
11. Tester Imprimer sous Windows.
12. Tester RLS école A / école B avec UUID connu : lecture/écriture inter-école impossible.
