#!/usr/bin/env sh
set -eu
[ -f .env ] || { echo '.env manquant'; exit 1; }
docker compose up -d postgres redis
docker compose run --rm migrator
docker compose run --rm migrator python scripts/g2_offline_finance_protocol_probe.py
node ./frontend/verify-offline-hash.mjs
echo 'G2 PROTOCOL: PASS si les deux lignes PASS ci-dessus sont visibles.'
echo 'Le gate du ledger Finance canonique reste distinct.'
