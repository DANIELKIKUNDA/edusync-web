# Point 10H7 — Pagination & synthèses mensuelles

- Annuaire élèves et familles: pagination serveur bornée à 50 lignes par page, conservation recherche/filtres, précédent/suivant.
- API schooling: `has_more`, `limit`, `offset`; lecture à `limit+1` sans requête COUNT coûteuse sur chaque frappe.
- Les exports certifiés restent indépendants de la page visible et conservent le périmètre filtré complet.
- Recouvrement: les synthèses Section et École acceptent désormais un mois précis (`period_order`) ou Toute l’année.
- Le filtrage mensuel est exécuté en SQL sur l’obligation financière (`period_order`, fallback mois de `due_date`), pas après agrégation côté navigateur.
- PDF/Excel des synthèses utilisent le même filtre mensuel que l’écran.
- La synthèse École mensuelle agrège les sections pour le seul mois choisi; la synthèse Section mensuelle agrège ses classes pour le seul mois choisi.

Gates machine inchangés: build frontend réel, PostgreSQL/Redis live, charge k6 et parité documentaire Finance Desktop là où `DESKTOP_GOLDEN_REQUIRED` subsiste.
