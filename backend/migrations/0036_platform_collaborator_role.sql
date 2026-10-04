-- Point 14 — collaboration Atelier Pro à privilèges limités.
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version)
VALUES ('platform.collaborators.manage','Atelier Pro','Accès plateforme','Gérer les collaborateurs de plateforme','manage','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,true,'Réservé au Manager système pour déléguer sans transmettre tous ses pouvoirs.','0.49')
ON CONFLICT (code) DO UPDATE SET source_status='OWNER_APPROVED',updated_at=now();

INSERT INTO rbac_roles(code,label,description,level,kind,status)
VALUES ('COLLABORATEUR_PLATEFORME','Collaborateur plateforme','Second rôle Atelier Pro à privilèges limités pour seconder le Manager système.','PLATFORM','PLATFORM_STANDARD','ACTIVE')
ON CONFLICT DO NOTHING;

INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,c.code FROM rbac_roles r JOIN capability_catalog c ON c.code IN ('platform.schools.read','platform.audit.read','platform.health.read')
WHERE r.code='COLLABORATEUR_PLATEFORME' AND r.kind='PLATFORM_STANDARD' AND r.status='ACTIVE'
ON CONFLICT DO NOTHING;

INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,'platform.collaborators.manage' FROM rbac_roles r
WHERE r.code='MANAGER_SYSTEME' AND r.kind='PLATFORM_STANDARD' AND r.status='ACTIVE'
ON CONFLICT DO NOTHING;
