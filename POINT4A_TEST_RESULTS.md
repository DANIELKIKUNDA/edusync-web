# Point 4A — Résultats de tests

Date: 2026-09-12

- `pytest -q` : **140 passed, 0 failed**.
- `python -m compileall -q src tests` : PASS.
- parsing de tous les JSON sous `contracts/` : PASS.
- `node --check frontend/public/sw.js` : PASS.
- `node --check frontend/verify-offline-hash.mjs` : PASS.
- transpilation syntaxique TypeScript via TypeScript global : **3 fichiers PASS**.
- OpenAPI Settings : **25 chemins** exposés.

Le `tsc -p tsconfig.json --noEmit` complet n'est pas certifiable dans ce conteneur car les dépendances React et `@types/*` ne sont pas installées localement. Cela ne doit pas être interprété comme un PASS TypeScript strict ; le build complet reste à exécuter dans l'environnement Docker/Windows avec `npm install`.
