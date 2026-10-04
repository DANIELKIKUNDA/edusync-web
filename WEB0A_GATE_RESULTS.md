# WEB-0A — Résultats de validation

Date : 2026-09-11

## Source Desktop préservée

- Archive source : `b427a52c-cb13-4a39-87c5-90efadf15f24.zip`
- SHA-256 archive source : `50e618c388346c7ebb671c12e6080fafb77d262c8daa2ba9cde05bfd97f18b71`
- Empreinte de l'arborescence extraite pendant ce lot : `a9b113888647bfbd7f25953e5a6f2b64d343bb64df64129d2984a45847a092d0`
- Modification du Desktop : **AUCUNE**.

## Contrôles exécutés

- `python -m compileall -q src tests` : PASS.
- `pytest -q` : **13 PASS / 0 FAIL**.
- JSON frontend : PASS.
- syntaxe Service Worker : PASS.
- Docker Compose YAML : PASS.
- migration PostgreSQL : garde statique RLS + audit append-only + idempotence : PASS.

## Gates

| Gate | État | Commentaire |
|---|---|---|
| G0 Préservation | PASS | Desktop intact, doctrine et golden-master contract inclus. |
| WEB-0A structure DDD/Clean/Hexagonale | PASS | Domain/Application/Ports/Adapters séparés dans le nouveau socle. |
| G1 Tenant/IAM | PARTIEL | Schéma, RLS, rôles/permissions et Atelier Pro sont fondés. Le branchement PostgreSQL réel + JWT production reste le prochain sous-lot. |
| G2 Audit/Events | FONDATION PASS | Audit append-only + outbox contract. Worker réel prochain sous-lot. |
| G3 PWA/Offline | FONDATION PASS | Service worker + IndexedDB outbox. Sync serveur et conflits métier non encore activés. |
| G4 Migration Harness | NON DÉMARRÉ | Volontairement hors WEB-0A. |

## Interdictions maintenues

- aucun paiement offline définitif ;
- aucune réécriture Finance ;
- aucune suppression ou simplification d'export ;
- aucune migration de la base Desktop ;
- aucune fusion avec la grande plateforme multi-organisation ;
- aucune logique Intendance injectée dans Finance.

## Verdict

**WEB-0A FONDATION TECHNIQUE ACQUISE.**

Ce verdict ne signifie pas encore « prêt production ». Le prochain lot doit fermer le Gate G1 avec PostgreSQL réel, sessions tenant, authentification JWT, permissions effectives et tests d'isolation multi-école sur une vraie instance PostgreSQL.
