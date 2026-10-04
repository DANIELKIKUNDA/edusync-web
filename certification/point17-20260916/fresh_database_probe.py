"""Apply the complete current provisioner on a separate empty local database."""
import importlib.util,json,os
from pathlib import Path
from sqlalchemy import create_engine,text
from sqlalchemy.engine import make_url
from edusync.bootstrap.settings import Settings
root=Path(__file__).resolve().parents[2];cfg=Settings()
owner=make_url(cfg.owner_database_url)
assert owner.host=='127.0.0.1' and owner.port==55432 and owner.database=='edusync_certification'
name='edusync_certification_fresh_20260917'
engine=create_engine(owner,isolation_level='AUTOCOMMIT')
with engine.connect() as c:
 exists=c.execute(text('SELECT 1 FROM pg_database WHERE datname=:n'),{'n':name}).first()
 if not exists:c.exec_driver_sql('CREATE DATABASE '+name)
for key in ('OWNER','TENANT','PLATFORM'):
 env='EDUSYNC_'+key+'_DATABASE_URL'
 os.environ[env]=make_url(os.environ[env]).set(database=name).render_as_string(hide_password=False)
spec=importlib.util.spec_from_file_location('cert_provision',root/'backend/scripts/provision_database.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.main()
fresh=create_engine(owner.set(database=name))
with fresh.connect() as c:
 versions=[r[0] for r in c.execute(text('SELECT version FROM schema_migrations ORDER BY version'))]
 view=c.execute(text("SELECT reloptions FROM pg_class WHERE oid='finance_charge_effective'::regclass")).scalar_one()
 roles=[dict(r) for r in c.execute(text("SELECT rolname,rolsuper,rolbypassrls FROM pg_roles WHERE rolname IN ('edusync_tenant','edusync_platform')")).mappings()]
 tables=[dict(r) for r in c.execute(text("SELECT c.relname,c.relrowsecurity,c.relforcerowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind='r' AND EXISTS(SELECT 1 FROM pg_attribute a WHERE a.attrelid=c.oid AND a.attname='school_id' AND NOT a.attisdropped) ORDER BY c.relname")).mappings()]
assert len(versions)==len(list((root/'backend/migrations').glob('*.sql')))
assert 'security_invoker=true' in view
assert all(not r['rolsuper'] and not r['rolbypassrls'] for r in roles)
assert all(t['relrowsecurity'] and t['relforcerowsecurity'] for t in tables)
report={'database':name,'migrations':versions,'roles':roles,'tenant_tables':tables,'finance_view_options':view,'pass':True}
(root/'certification/point17-20260916/fresh-database.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(f'PASS fresh database: {len(versions)} migrations, {len(tables)} tenant tables with FORCE RLS')
