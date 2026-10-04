"""Validate migration SQL on the isolated empty DB, rolling back all changes."""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]
env = os.environ.copy()
env['PGPASSWORD'] = (ROOT / '.local/postgres-certification-password').read_text(encoding='utf-8').strip()
env['PGCLIENTENCODING'] = 'UTF8'
lines = [
    r'\set ON_ERROR_STOP on', 'BEGIN;',
    'CREATE ROLE edusync_tenant NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;',
    'CREATE ROLE edusync_platform NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS;',
]
for path in sorted((ROOT / 'backend/migrations').glob('*.sql')):
    lines += [f'\\echo MIGRATION {path.name}', f"\\i '{path.as_posix()}'"]
lines += ['ROLLBACK;']
script = ROOT / '.local/probe-migrations.sql'
script.write_text('\n'.join(lines), encoding='utf-8')
result = subprocess.run([
    r'C:\Program Files\PostgreSQL\16\bin\psql.exe', '-X', '-w',
    '-h', '127.0.0.1', '-p', '55432', '-U', 'edusync_cert_owner',
    '-d', 'edusync_certification', '-f', str(script),
], env=env, capture_output=True)
log = ROOT / 'certification/point17-20260916/sql-migration-probe.log'
log.write_bytes(result.stdout + result.stderr)
print(result.stdout.decode('utf-8', errors='replace')[-1500:])
print(result.stderr.decode('utf-8', errors='replace')[-2500:])
raise SystemExit(result.returncode)
