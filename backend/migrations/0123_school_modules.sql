-- EduSync V2, lot 0 — modules per school (owner, 2026-11-22).
-- « Chaque école n'aura pas la V2 : on va la vendre séparément » and « il faut permettre aux écoles existantes qui n'ont
-- pas de module de leur donner des modules ».
--   * the eight modules of V1 are RECORDED for every existing school (source MIGRATION) — recorded, not enforced:
--     nothing changes for any user;
--   * the pedagogy module (catalogue code ACADEMIC) is the one module the server ENFORCES; no school has it by default,
--     the platform grants it school by school (source MANUAL), no payment involved (subscriptions paused, 2026-11-22);
--   * two platform capabilities: read / manage the modules of a school (MFA step-up for manage).
-- Additive only: no table, column or row of a school is removed. Safe to run twice.

UPDATE saas_modules
   SET label='Pédagogie (référentiel, cotes, bulletins)',
       description='Module V2 vendu séparément : référentiel officiel MINEDUC, calendrier, enseignants, cotes, bulletins et proclamation.',
       version=version+1, updated_at=now()
 WHERE code='ACADEMIC' AND label<>'Pédagogie (référentiel, cotes, bulletins)';

-- Every existing school keeps what it already uses: the eight V1 modules, recorded once.
INSERT INTO saas_entitlements(school_id,module_code,source,status,reason)
SELECT s.id, m.code, 'MIGRATION', 'ACTIVE', 'Module V1 déjà en service avant la gestion des modules (lot 0, 22/11/2026)'
  FROM schools s
 CROSS JOIN (VALUES ('CORE_SCHOOL'),('ENROLLMENT'),('FINANCE'),('RECOVERY'),('REPORTS'),('PERSONNEL'),('DOCUMENTS'),('COMMUNICATIONS')) AS m(code)
 WHERE NOT EXISTS (SELECT 1 FROM saas_entitlements e WHERE e.school_id=s.id AND e.module_code=m.code AND e.status='ACTIVE');

INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version)
VALUES
 ('platform.school_modules.read','Atelier Pro','Écoles','Voir les modules d’une école','read','MEDIUM','SERVER_ONLY',false,'["PLATFORM"]','OWNER_APPROVED','[]','[]',false,'Modules en service et historique','3.0.0'),
 ('platform.school_modules.manage','Atelier Pro','Écoles','Activer ou retirer un module d’une école','manage','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]','OWNER_APPROVED','[]','[]',true,'Motif et code de confirmation obligatoires','3.0.0')
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label, risk=EXCLUDED.risk, audit_required=EXCLUDED.audit_required,
  notes=EXCLUDED.notes, registry_version=EXCLUDED.registry_version, active=true, updated_at=now();

INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,c.code FROM rbac_roles r CROSS JOIN capability_catalog c
 WHERE r.code='MANAGER_SYSTEME' AND r.level='PLATFORM' AND c.code IN ('platform.school_modules.read','platform.school_modules.manage')
ON CONFLICT DO NOTHING;
-- The platform collaborator already sees the schools: it may also see their modules (never change them).
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,'platform.school_modules.read' FROM rbac_roles r
 WHERE r.code='COLLABORATEUR_PLATEFORME' AND r.level='PLATFORM' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
