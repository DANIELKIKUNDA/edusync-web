"""Explicit test-only import permissions; never changes any standard role."""
from pathlib import Path
import json
from sqlalchemy import create_engine,text
from edusync.bootstrap.settings import Settings

root=Path(__file__).resolve().parents[2]
cfg=Settings()
assert ':55432/edusync_certification' in cfg.owner_database_url
fixtures=json.loads((root/'.local/http-fixtures.json').read_text(encoding='utf-8'))
engine=create_engine(cfg.owner_database_url)
with engine.begin() as c:
 for fixture in fixtures.values():
  rid=c.execute(text("SELECT id FROM rbac_roles WHERE school_id=:s AND code='CERT_IMPORT'"),{'s':fixture['school_id']}).scalar_one_or_none()
  if rid is not None:
   c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,'documents.student_import_template.export') ON CONFLICT DO NOTHING"),{'r':rid})
   continue
  rid=c.execute(text("INSERT INTO rbac_roles(school_id,code,label,level,kind,status) VALUES(:s,'CERT_IMPORT','Recette imports uniquement','SCHOOL','SCHOOL_CUSTOM','ACTIVE') RETURNING id"),{'s':fixture['school_id']}).scalar_one()
  for kind in ('students','staff','finance_history'):
   for action in ('analyze','execute'):
    c.execute(text('INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,:p)'),{'r':rid,'p':f'migration.{kind}.{action}'})
  aid=c.execute(text("INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,reason) VALUES(:u,:r,:s,:m,'Recette isolée : permission explicite des imports') RETURNING id"),{'u':fixture['user_id'],'r':rid,'s':fixture['school_id'],'m':fixture['membership_id']}).scalar_one()
  c.execute(text("INSERT INTO rbac_assignment_scopes(assignment_id,scope_type) VALUES(:a,'SCHOOL')"),{'a':aid})
  c.execute(text("INSERT INTO rbac_role_capabilities(role_id,capability_code) VALUES(:r,'documents.student_import_template.export') ON CONFLICT DO NOTHING"),{'r':rid})
print('Test-only school-scoped import roles seeded; standard roles unchanged.')
