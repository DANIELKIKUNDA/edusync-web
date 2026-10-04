$ErrorActionPreference = "Stop"
Write-Host "=== EduSync Point 2 / Finance offline multi-caissier ==="
if (-not (Test-Path ".env")) { throw "Fichier .env manquant. Copiez .env.example vers .env et renseignez les secrets." }

Push-Location .\backend
python -m pytest -q
Pop-Location

docker compose up -d postgres redis
docker compose run --rm migrator
docker compose run --rm migrator python scripts/g1_postgres_probe.py
docker compose run --rm migrator python scripts/g3_multi_cashier_probe.py

node .\frontend\verify-offline-hash.mjs
tsc -p .\frontend\tsconfig.finance-offline.json --noEmit

Write-Host "POINT2 LOCAL+LIVE: PASS si pytest, G1, G3, hash et TypeScript sont PASS."
Write-Host "Le probe G3 est réservé à la base Docker/dev jetable, jamais à la production."
