# Point 4C — Résultats de tests après correction de préservation

- `pytest` : **206 passed / 0 failed**
- `python -m compileall -q src tests` : **PASS**
- TypeScript syntaxique : **3/3 PASS** (`schooling.tsx`, `api.ts`, `App.tsx`)
- Documents canoniques générés : liste élèves PDF/XLSX + répertoire familles PDF/XLSX
- PDF canoniques re-rendus et inspectés : **2/2 PASS**
- XLSX liste élèves importé avec `artifact_tool` et rendu visuel : **PASS**
- Colonnes liste élèves : **12/12 exactes**
- Sexe obligatoire : **PASS**
- Date et lieu de naissance optionnels par défaut : **PASS**

Limite : PostgreSQL/Docker/RLS live, build React complet et impression réelle ne sont pas déclarés PASS dans ce sandbox.
