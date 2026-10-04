# Point 10H12 — Fermeture locale Synchronisation

Date: 2026-09-15
Version: 0.29.0-point10h12

## Fermé dans cette passe
- Frontend exploite la pagination keyset des opérations rejetées avec `next_cursor` et « Charger plus ».
- Frontend affiche l'outbox PostgreSQL durable en attente, également paginée par keyset.
- Séparation UI entre diagnostics/rejets `sync_inbox` et vrais conflits métier `sync_conflicts`.
- Nouvelle lecture des conflits ouverts à arbitrer depuis `sync_conflicts`.
- Résolution/classification serveur avec permission critique `sync.conflicts.resolve`.
- Résolution fail-closed : tenant obligatoire, verrou `FOR UPDATE`, conflit inexistant = 404, déjà arbitré = 409.
- Justification obligatoire (5–1000 caractères), auteur et date de résolution conservés.
- Événement d'audit append-only `sync.conflict.resolved`.
- Dialogue React dédié ; aucun `window.prompt/confirm/alert` introduit.

## Validation locale
- pytest : 362/362 PASS.
- `python -m compileall -q src` : PASS.

## Gates non revendiqués
- Build Vite/TypeScript réel non certifié dans cette passe.
- PostgreSQL/RLS/Redis multi-process réels restent au Point 11.
- Résolution métier ne réécrit pas automatiquement l'objet métier : l'arbitrage clôt le conflit et le trace. Toute stratégie de merge/replay automatique doit rester spécifique au type d'agrégat et ne doit pas être inventée génériquement.
