#!/usr/bin/env sh
set -eu
[ -f .env ] || { echo '.env manquant'; exit 1; }
(cd backend && python -m pytest -q)
docker compose up -d postgres redis
docker compose run --rm migrator
docker compose run --rm migrator python scripts/g1_postgres_probe.py
docker compose run --rm migrator python scripts/g3_multi_cashier_probe.py
node ./frontend/verify-offline-hash.mjs
tsc -p frontend/tsconfig.finance-offline.json --noEmit
echo 'POINT2 LOCAL+LIVE: PASS si pytest, G1, G3, hash et TypeScript sont PASS.'
