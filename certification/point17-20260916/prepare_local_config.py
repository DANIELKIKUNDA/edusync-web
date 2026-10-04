"""Generate private credentials for the isolated local certification instance."""
from pathlib import Path
import secrets

ROOT = Path(__file__).resolve().parents[2]
target = ROOT / '.local' / 'certification.env'
if target.exists():
    raise SystemExit('Private configuration already exists; left unchanged.')
owner = (ROOT / '.local' / 'postgres-certification-password').read_text(encoding='utf-8').strip()
values = {
    'EDUSYNC_ENV': 'dev',
    'EDUSYNC_OWNER_DATABASE_URL': f'postgresql+psycopg://edusync_cert_owner:{owner}@127.0.0.1:55432/edusync_certification',
    'EDUSYNC_TENANT_DATABASE_URL': f'postgresql+psycopg://edusync_tenant:{secrets.token_urlsafe(36)}@127.0.0.1:55432/edusync_certification',
    'EDUSYNC_PLATFORM_DATABASE_URL': f'postgresql+psycopg://edusync_platform:{secrets.token_urlsafe(36)}@127.0.0.1:55432/edusync_certification',
    'EDUSYNC_JWT_SECRET': secrets.token_urlsafe(48),
    'EDUSYNC_REDIS_URL': 'redis://127.0.0.1:6379/15',
    'EDUSYNC_PLATFORM_ADMIN_EMAIL': 'certification@example.test',
    'EDUSYNC_PLATFORM_ADMIN_PASSWORD': secrets.token_urlsafe(36),
    'EDUSYNC_PLATFORM_ADMIN_NAME': 'Certification locale',
    'EDUSYNC_API_BASE_URL': 'http://127.0.0.1:58000/api/v1',
    'EDUSYNC_CORS_ORIGINS': 'http://localhost:5173,http://127.0.0.1:5173',
}
target.write_text(''.join(f'{key}={value}\n' for key, value in values.items()), encoding='utf-8')
print('Private configuration generated in .local; no credentials printed.')
