# EduSync — Point 10H11 — Fermeture locale sécurité/API

Version 0.28.0-point10h11.

Durcissements : garde HTTP précoce (corps 2 MiB, query-string 8 KiB), cache interdit sur `/api/*`, configuration production CORS/TrustedHost fail-closed, régressions IDOR/BOLA sur contexte école et membership, contrôle statique de paramétrage SQL sur routes sensibles.

Validation locale : suite pytest complète PASS et `python -m compileall -q src` PASS.

Non certifié localement : attaques dynamiques cross-tenant, SQLi/XSS réels, proxy/chunked, brute force distribué, audits dépendances/SAST et comportement sous stack PostgreSQL/Redis/Docker réelle. Ces gates restent pour la certification machine.
