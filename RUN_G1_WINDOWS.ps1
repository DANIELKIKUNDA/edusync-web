$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
    Write-Host "Le fichier .env vient d'être créé." -ForegroundColor Yellow
    Write-Host "Remplace d'abord tous les secrets CHANGE_... dans .env, puis relance ce script." -ForegroundColor Yellow
    exit 2
}

$envText = Get-Content ".env" -Raw
if ($envText -match "CHANGE_(OWNER|TENANT|PLATFORM)_PASSWORD|CHANGE_ME_NOW|CHANGE_WITH_AT_LEAST") {
    throw "Secrets placeholders détectés dans .env. Remplace-les avant la certification G1."
}

Write-Host "[1/4] Construction et démarrage WEB-0C..." -ForegroundColor Cyan
docker compose up -d --build

Write-Host "[2/4] État des services..." -ForegroundColor Cyan
docker compose ps

Write-Host "[3/4] Probe PostgreSQL/RLS/concurrence/idempotence..." -ForegroundColor Cyan
docker compose run --rm migrator python scripts/g1_live_certification.py

Write-Host "[4/4] Probe API JWT/RBAC + double-submit concurrent..." -ForegroundColor Cyan
docker compose run --rm -e EDUSYNC_API_BASE_URL=http://backend:8000/api/v1 migrator python scripts/g1_api_probe.py

Write-Host "G1 WEB-0C terminé. Conserve la sortie complète pour la certification." -ForegroundColor Green
