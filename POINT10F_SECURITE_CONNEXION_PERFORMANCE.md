# Point 10F — Sécurité, connexion et performance perçue

- Page de connexion modernisée, responsive, sans message technique.
- Validation login avec React Hook Form + Zod; erreurs de champs homogènes et accessibles.
- Réponse d'authentification volontairement non révélatrice: pas d'énumération compte/école/adhésion.
- Anti-bruteforce distribué Redis: fenêtre 15 min, 7 échecs, verrou temporaire 15 min; clés hachées, Retry-After.
- JWT PyJWT conservé, Argon2 conservé, secrets de développement interdits en production.
- En-têtes de sécurité applicatifs: CSP, frame deny, nosniff, referrer policy, permissions policy, COOP/CORP, HSTS sous HTTPS; réponses auth no-store.
- TrustedHost configuré; CORS reste allowlisté.
- Chargement des gros modules React à la demande avec Suspense; Effectifs reste eager pour préserver le contrat de certification Point 4D.
- Loader métier non technique pendant le chargement d'un module.
- Aucun changement de règles métier Finance/Effectifs/Documents/Intendance.

Validation locale: pytest 322/322 PASS; compileall PASS.
Frontend build: non exécuté si node_modules absent.
Gates Point 11: navigateur Windows réel, HTTPS/reverse proxy, Redis live anti-bruteforce, PostgreSQL live/RLS/concurrence, tests de pénétration et CSP en production.
