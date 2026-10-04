# Point 3B — Addendum — Direction des études et Direction de discipline

Date : 2026-09-12

## Décision propriétaire

Deux rôles standards supplémentaires existent uniquement dans la **section Secondaire**.

### Directeur des études (`DIRECTEUR_ETUDES`)

- suivi pédagogique/scolaire et consultation dans le Secondaire ;
- consultation élèves, effectifs, personnel du périmètre, documents, tableaux de bord et communications ciblées ;
- impression/export des vues utiles ;
- **aucune permission Finance dans la baseline** ;
- la lecture Finance peut être ajoutée explicitement par l'école via une permission/variante de rôle, sans donner d'écriture financière.

### Directeur de discipline (`DIRECTEUR_DISCIPLINE`)

- suivi quotidien des élèves dans le Secondaire ;
- consultation des responsables/familles et du personnel utile du périmètre ;
- communication forte avec les parents : individuel, classe, section, SMS et bulk ciblé au périmètre ;
- impression/export des vues utiles ;
- aucune Finance dans la baseline.

## Garde de périmètre

`PREFET_ETUDES`, `DIRECTEUR_ETUDES` et `DIRECTEUR_DISCIPLINE` sont limités à `SECTION=SECONDAIRE`. La migration ajoute un trigger PostgreSQL qui refuse une affectation de ces rôles à Maternelle, Primaire ou à un scope racine école.

## Doctrine

Ces rôles restent des paquets de capacités du moteur RBAC. Une école qui veut une variante crée un rôle personnalisé ou ajoute les permissions explicitement autorisées ; le code métier ne teste jamais le titre du poste.
