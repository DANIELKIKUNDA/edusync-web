"""Run existing tools against the isolated local certification configuration.

Examples: python run_local.py backend/scripts/provision_database.py
          python run_local.py -m uvicorn edusync.bootstrap.app:create_app --factory --port 58000
No secrets are printed; configuration is private under .local.
"""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
for line in (ROOT / '.local' / 'certification.env').read_text(encoding='utf-8').splitlines():
    if line and not line.startswith('#'):
        key, value = line.split('=', 1)
        os.environ[key] = value
os.environ['PYTHONUTF8'] = '1'
os.environ['PYTHONPATH'] = str(ROOT / 'backend' / 'src')
raise SystemExit(subprocess.call([str(ROOT / '.venv' / 'Scripts' / 'python.exe'), *sys.argv[1:]], cwd=ROOT))
