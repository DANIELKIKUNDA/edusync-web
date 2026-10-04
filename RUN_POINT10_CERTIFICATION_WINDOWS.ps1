$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
Write-Host '[1/4] Python compileall'
python -m compileall -q backend/src
Write-Host '[2/4] Backend automated suite'
Push-Location backend; pytest -q; Pop-Location
Write-Host '[3/4] Transversal static contracts'
python -c "from pathlib import Path; s=Path('backend/src/edusync/bootstrap/app.py').read_text(); assert all(x in s for x in ['/api/v1/audit','/api/v1/notifications','/api/v1/sync','/api/v1/stewardship']); print('Static contracts PASS')"
Write-Host '[4/4] Frontend build gate'
if (Test-Path 'frontend/node_modules') { Push-Location frontend; npm run build; Pop-Location } else { Write-Host 'SKIP: frontend/node_modules absent - gate remains OPEN' }
