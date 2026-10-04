# Point 10H5 — fermeture Sync / Intendance

## Corrigé
- Intendance: correction d'une incohérence réelle `tag`/`asset_tag` qui aurait cassé la création d'un bien sur PostgreSQL.
- Validation d'inventaire fail-closed: inventaire inexistant, déjà validé ou vide refusé avant toute correction de stock.
- Lecture des types de biens, liste et détail des inventaires ajoutés.
- Frontend Intendance branche désormais la liste réelle des inventaires au lieu du placeholder statique.
- Clients API ajoutés pour création/état des biens et cycle de comptage.
- Synchronisation: surface d'administration ajoutée au shell, visible uniquement avec capacités `sync.*`.
- Appareils: état, enregistrement et révocation; conflits/rejets consultables selon RBAC.
- Aucun `window.alert/prompt/confirm` ni `String(e)/String(err)` dans `frontend/src`.

## Validation locale
- pytest: 341/341 PASS.
- `python -m compileall -q backend/src`: PASS.

## Gates réels non falsifiés
- PostgreSQL + FORCE RLS en exécution réelle.
- Redis réel, panne/reprise et charge.
- Build React/npm et tests navigateur Windows.
- k6 p95/p99 et EXPLAIN ANALYZE sur jeu de données représentatif.
- Fournisseur SMS réel et parité documentaire Finance Desktop.
