# Point 10 — Consolidation vers la certification automatisée

## Résultat local
- Python `compileall`: PASS.
- Suite backend: **306/306 PASS**.
- Contrats statiques transversaux: PASS.
- Build React/TypeScript: **OPEN / non exécuté** car `frontend/node_modules` est absent.
- PostgreSQL réel, RLS live, concurrence multi-caissier, navigateur Windows, impression et réseau: restent des gates d'environnement.

## Transversal industrialisé
### Audit
- API globale `/api/v1/audit` hors Centre financier.
- Journal école en lecture seule, filtrage permissionné, historique d'entité.
- Aucun droit d'audit n'est déduit d'un titre de poste.

### Notifications internes
- API `/api/v1/notifications`.
- Lecture personnelle par défaut; marquage traité limité au destinataire.
- Création réservée à la capacité explicite correspondante et destinataire obligatoirement membre actif de l'école.

### Synchronisation
- API de statut `/api/v1/sync/status`.
- Expose l'état de l'outbox et des appareils sans modifier la doctrine financière offline.
- `AUTHORIZED_PARTITIONED_CASH_V2`, pas de fusion financière automatique.

## RBAC
Les dashboards et modules restent gouvernés par les capacités effectives. Directeur des études / Directeur de discipline n'obtiennent aucune finance par simple intitulé; un bloc financier n'est légitime que si l'établissement accorde explicitement la capacité correspondante.

## Préservation
Le contrat de santé historique Point 4D est volontairement conservé car des tests de non-régression le figent. Le Point 10 étend le système sans casser ce golden contract.

## Scripts
- `RUN_POINT10_CERTIFICATION_LINUX.sh`
- `RUN_POINT10_CERTIFICATION_WINDOWS.ps1`
