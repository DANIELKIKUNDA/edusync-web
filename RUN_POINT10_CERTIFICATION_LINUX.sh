#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
echo '[1/4] Python compileall'
python -m compileall -q backend/src
echo '[2/4] Backend automated suite'
(cd backend && pytest -q)
echo '[3/4] Transversal static contracts'
python - <<'PY'
from pathlib import Path
r=Path('.')
app=(r/'backend/src/edusync/bootstrap/app.py').read_text()
assert 'POINT-4D-EFFECTIFS-DEPOTS' in app
for x in ['/api/v1/audit','/api/v1/notifications','/api/v1/sync','/api/v1/stewardship']: assert x in app
home=(r/'frontend/src/home.tsx').read_text()
assert 'finance.recovery.read' in home or 'finance.analysis.by_fee.read' in home
print('Static contracts PASS')
PY
echo '[4/4] Frontend build gate'
if [ -d frontend/node_modules ]; then (cd frontend && npm run build); else echo 'SKIP: frontend/node_modules absent — gate remains OPEN'; fi
