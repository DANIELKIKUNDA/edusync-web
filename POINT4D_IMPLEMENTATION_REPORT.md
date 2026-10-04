# EduSync — Point 4D — Effectifs & Dépôts Web

## État

Portage preservation-first implémenté à partir des preuves Desktop certifiées. Version API/front : `0.9.0-point4d`.

## Backend

Nouveau module `edusync.modules.effectifs` et adaptateur PostgreSQL :

- synthèse KPI annuelle ;
- agrégations par classe, section et filière/option ;
- quatre projections F/G/T ;
- mouvements annuels avec filtres et pagination ;
- classes disponibles filtrées par périmètre ;
- registre des dépôts matériels ;
- saisie append-only, idempotente, auditée et outbox ;
- exports PDF/Excel ;
- impression par PDF ;
- 10 routes `/api/v1/effectifs/*`.

La portée demandée par l'écran est toujours intersectée avec la portée de la capacité RBAC. Pour un export, la portée de lecture du regroupement est autoritative : une permission d'export plus large ne peut pas élargir les données.

## PostgreSQL

Migration `0015_effectifs_depots_domain.sql` :

- `material_contributions` ;
- contrôle année `ACTIVE` ;
- cohérence école/année/élève/inscription/type de contribution ;
- FORCE RLS ;
- interdiction UPDATE/DELETE ;
- correction conditionnelle du défaut Point 4C sur le sexe obligatoire.

## Frontend

La page reproduit le module validé : sélecteur de périmètre, 3 KPI, quatre onglets Effectifs, actions Imprimer/PDF/Excel, grille groupée 14 colonnes et total général. Les icônes sont SVG, les valeurs sont centrées et les micro-animations respectent `prefers-reduced-motion`.

Le registre Dépôts matériels conserve le même périmètre et dispose de recherche, export Excel et saisie guidée quand la permission `contributions.record` est présente.

## Documents

Le PDF de contrôle a été rendu à 180 DPI : A4 paysage, groupes centrés, aucune cellule noire, aucun texte coupé ou chevauché. Le classeur de contrôle reproduit 14 colonnes, titres groupés et total général.

## Limites assumées

Ce lot ne crée ni gestion d'achats, ni inventaire, ni stock attendu : ces notions appartiennent au futur BC Intendance. Il ne crée aucune nouvelle catégorie de mouvement scolaire.
