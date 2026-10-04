-- EduSync Point 3B — owner decision 01
-- Daniel approved MANAGER_SYSTEME and added platform system notifications.

INSERT INTO capability_catalog(
  code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,
  scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version
) VALUES (
  'platform.notifications.system.send','Atelier Pro','Notifications système',
  'Envoyer une notification système aux écoles/utilisateurs ciblés','send','HIGH','SERVER_ONLY',true,
  '["PLATFORM"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,true,
  'Capacité validée par Daniel pour le Manager système; ciblage et contenu audités.','0.2-owner-decisions'
)
ON CONFLICT (code) DO UPDATE SET
  domain_name=EXCLUDED.domain_name,group_name=EXCLUDED.group_name,label=EXCLUDED.label,
  action_code=EXCLUDED.action_code,risk=EXCLUDED.risk,offline_policy=EXCLUDED.offline_policy,
  audit_required=EXCLUDED.audit_required,scope_types=EXCLUDED.scope_types,source_status=EXCLUDED.source_status,
  prerequisites=EXCLUDED.prerequisites,outputs=EXCLUDED.outputs,sensitive=EXCLUDED.sensitive,
  notes=EXCLUDED.notes,registry_version=EXCLUDED.registry_version,updated_at=now();

-- Keep the standard platform role global and owner-controlled.
UPDATE rbac_roles
SET status='OWNER_APPROVED', version=version+1, updated_at=now()
WHERE code='MANAGER_SYSTEME' AND kind='PLATFORM_STANDARD' AND status='DRAFT';

-- Owner approval is final for decision 01: activate the role.
UPDATE rbac_roles
SET status='ACTIVE', version=version+1, updated_at=now()
WHERE code='MANAGER_SYSTEME' AND kind='PLATFORM_STANDARD' AND status='OWNER_APPROVED';

-- Manager gets every Atelier Pro capability currently approved, including system notifications.
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,c.code
FROM rbac_roles r
JOIN capability_catalog c ON c.domain_name='Atelier Pro' AND c.active=true
WHERE r.code='MANAGER_SYSTEME' AND r.kind='PLATFORM_STANDARD' AND r.status='ACTIVE'
ON CONFLICT DO NOTHING;
