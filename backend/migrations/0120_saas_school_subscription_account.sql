-- EduSync SaaS S4: read-only subscription account inside the school space.
-- Commercial writes stay exclusively in Atelier Pro (platform.billing.*).
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,
  scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version)
VALUES ('subscription.account.read','Abonnement EduSync','Abonnement','Consulter l’abonnement, les factures et paiements de l’école',
  'read','MEDIUM','SERVER_ONLY',false,'["SCHOOL"]','OWNER_APPROVED','[]','[]',true,
  'Lecture strictement limitée à l’école du jeton; aucune mutation commerciale.','3.0.0')
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label,notes=EXCLUDED.notes,active=true,updated_at=now();

INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT id,'subscription.account.read' FROM rbac_roles
WHERE level='SCHOOL' AND code IN ('ADMIN_SYSTEME_ECOLE','PROMOTEUR','GESTIONNAIRE','RESPONSABLE_FINANCE')
ON CONFLICT DO NOTHING;

