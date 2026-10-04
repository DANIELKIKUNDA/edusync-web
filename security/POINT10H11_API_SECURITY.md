# Point 10H11 — Durcissement sécurité/API

## Fermé localement
- Bornes précoces sur taille du corps HTTP (2 MiB par défaut) et query-string (8 KiB).
- Réponses `/api/*` explicitement `no-store`/`no-cache` afin d'éviter la conservation de données scolaires/financières dans les caches navigateur/intermédiaires.
- Production fail-closed : CORS wildcard interdit, origines HTTP interdites, TrustedHost wildcard interdit.
- Régression statique IDOR/BOLA : le contexte école est repris du JWT signé puis revalidé contre utilisateur, école, membership, versions et permissions PostgreSQL ; les routes sensibles restent dans `tenant_transaction(school_id=actor.school_id, ...)`.
- Régression SQLi sur routes chaudes : requêtes SQL paramétrées, interdiction de SELECT interpolé par f-string dans le gate.

## À certifier sur infrastructure réelle
OWASP/API offensif : BOLA cross-tenant, JWT forgé/expiré/replay, XSS, SQLi dynamique, CORS/Host spoofing, brute force distribué, limites via chunked transfer/proxy, SAST et audits dépendances. Ces tests nécessitent la stack réellement démarrée et ne sont pas déclarés PASS ici.
