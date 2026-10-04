# WEB-0C — Résultats locaux

Date : 2026-09-11

```text
pytest: 41 passed
Python compileall: PASS
Docker Compose YAML parse: PASS
frontend package/manifest JSON parse: PASS
Service Worker node --check: PASS
TypeScript transpile syntax: 4/4 PASS
```

Le `tsc` complet n'est pas compté PASS ici car les dépendances React/Vite ne sont pas installées dans l'environnement d'audit. Le Dockerfile exécutera `npm install` puis `npm run build` pendant le gate live. Aucun résultat Docker/PostgreSQL live n'est inventé.
