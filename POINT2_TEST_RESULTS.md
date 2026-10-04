# Résultats de tests — Point 2

Date : 11 septembre 2026

- `pytest -q` : **100 passed**
- compilation `backend/src` + `backend/scripts` : **PASS**
- TypeScript strict ciblé `frontend/src/offline/financeJournal.ts` : **PASS**
- `node frontend/verify-offline-hash.mjs` : **OFFLINE_FINANCE_HASH_VECTOR_PASS**
- PostgreSQL live : **non disponible dans l'environnement ChatGPT** (`docker`, `psql`, `postgres` absents)
- probe live fourni : `backend/scripts/g3_multi_cashier_probe.py`

Le verdict local est PASS. Le gate live est explicitement laissé à la certification machine réelle conformément à la doctrine 99%/1% du projet.
