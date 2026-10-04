$ErrorActionPreference = "Stop"
Write-Host "=== EduSync WEB-0D / G2 Offline Finance Protocol ==="
if (-not (Test-Path ".env")) { throw "Fichier .env manquant. Copiez .env.example vers .env et renseignez les secrets." }

docker compose up -d postgres redis
docker compose run --rm migrator

docker compose run --rm migrator python scripts/g2_offline_finance_protocol_probe.py
node .\frontend\verify-offline-hash.mjs

Write-Host "G2 PROTOCOL: PASS si les deux lignes PASS ci-dessus sont visibles."
Write-Host "ATTENTION: cela ne remplace pas le futur gate du ledger Finance canonique."
