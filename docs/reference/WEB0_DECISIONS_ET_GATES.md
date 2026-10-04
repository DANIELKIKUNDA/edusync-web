# WEB-0 — Décisions d’architecture et gates

## Décisions gelées

| ID | Décision | Statut |
|---|---|---|
| ADR-001 | Hébergement sur VPS distant | GELÉ |
| ADR-002 | Produit multi-école sans couche Organisation | GELÉ |
| ADR-003 | Atelier Pro / super-admin plateforme | GELÉ |
| ADR-004 | DDD + Clean + Hexagonal | GELÉ |
| ADR-005 | Monolithe modulaire FastAPI | GELÉ |
| ADR-006 | PostgreSQL source de vérité | GELÉ |
| ADR-007 | React + TypeScript + PWA | GELÉ |
| ADR-008 | Redis pour cache/coordination, jamais vérité financière | GELÉ |
| ADR-009 | Multi-tenancy shared schema + school_id + RLS | GELÉ pour phase initiale |
| ADR-010 | RBAC par permissions | GELÉ |
| ADR-011 | Audit append-only industrialisé | GELÉ |
| ADR-012 | Notifications via événements + transactional outbox | GELÉ |
| ADR-013 | Offline-first à politiques par domaine | GELÉ |
| ADR-014 | Finance offline soumise à certification dédiée | GELÉ |
| ADR-015 | Exports Desktop = golden masters | GELÉ |
| ADR-016 | Générateurs Python réutilisés derrière ports si possible | GELÉ |
| ADR-017 | Import Web enrichissable avec staging/mapping | GELÉ |
| ADR-018 | Intendance = bounded context distinct | GELÉ |
| ADR-019 | Grande plateforme multi-organisation reste séparée | GELÉ |
| ADR-020 | Desktop conservé comme oracle de parité pendant migration | GELÉ |

## Gate G0 — Préservation

- archive source hashée ;
- golden data identifiés ;
- golden exports identifiés ;
- matrice des modules approuvée ;
- aucune modification du Desktop.

## Gate G1 — Tenant/IAM

- deux écoles ;
- utilisateurs/memberships ;
- permissions ;
- isolation API ;
- RLS ;
- Atelier Pro minimal.

## Gate G2 — Audit/Events

- audit transactionnel ;
- outbox ;
- worker ;
- notification in-app ;
- correlation IDs ;
- append-only.

## Gate G3 — PWA/Offline Foundation

- app shell offline ;
- LocalStorePort ;
- client outbox ;
- server inbox/idempotence ;
- sync cursor ;
- conflit non financier démontré.

## Gate G4 — Migration Harness

- lecture seule SQLite v17 ;
- migration école pilote ;
- counts ;
- réconciliation financière ;
- audit migration ;
- rollback staging.

## Gate G5 — Premier domaine porté

Premier domaine recommandé : Paramètres + identité école + années + utilisateurs, car il permet de valider la fondation multi-école sans exposer d’abord la Finance à un risque de régression.

## Interdictions avant G0-G4

- réécrire les règles financières ;
- supprimer des exports ;
- changer les numéros historiques ;
- fusionner plan anticipé et fonds anticipé ;
- autoriser un paiement offline final non certifié ;
- ajouter Intendance dans les tables Finance ;
- exposer une école à une autre ;
- déployer une migration non testée directement en production.
