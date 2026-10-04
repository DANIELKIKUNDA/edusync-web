# Point 9 — Intendance industrielle

## Périmètre livré
- bounded context Intendance activé sous `/api/v1/stewardship`;
- patrimoine durable avec états, localisation et historique d'événements;
- locaux avec capacité et état opérationnel;
- consommables avec unité, stock réel, seuil faible et emplacement;
- entrées/sorties/ajustements tracés, motif obligatoire, destination/référence;
- protection stock négatif et verrouillage pessimiste à la mutation;
- inventaires physiques structurés (DRAFT/VALIDATED, théorique vs compté);
- stocks destinés à la vente reliés au stock Point 6B, sans seconde vérité;
- prix courants restent dans `school_products` / Paramètres et encaissement reste Finance;
- dashboard Intendance alimenté par vrais read-models, sans KPI fictif;
- UI Intendance permission-driven: vue d'ensemble, consommables, patrimoine & locaux, articles vendus, mouvements, inventaires;
- RLS + FORCE RLS sur les nouvelles tables.

## Permissions
Intendance est une capacité, pas un titre obligatoire. Le module n'apparaît que si l'utilisateur possède une capacité `inventory.*`. Il peut donc être confié à un Intendant, Préfet, Directeur, Administrateur ou autre utilisateur autorisé.

Durcissement confirmé: `DIRECTEUR_ETUDES` et `DIRECTEUR_DISCIPLINE` n'ont ni Finance ni Personnel dans leur baseline. Une école peut ajouter des droits explicitement via le moteur RBAC/exception grants.

## Cohérence Finance
Le stock des articles vendus existant (`inventory_stock`) reste l'autorité utilisée par le checkout Finance. Point 9 le consulte; il ne crée pas un stock parallèle. Une vente diminue le stock via le flux financier déjà industrialisé.

## Validation locale
- pytest: 301/301 PASS
- Python compileall: PASS
- PostgreSQL live/RLS/concurrence: non certifié dans cet environnement
- build React/TypeScript complet: non certifié si dépendances npm absentes
- certification Windows/browser: reste gate final
