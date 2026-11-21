-- Paiement des abonnements EduSync par Mobile Money : aucune donnée de caisse scolaire n'est concernée.
ALTER TABLE saas_payments
  ADD COLUMN IF NOT EXISTS expires_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_provider_update_at timestamptz,
  ADD COLUMN IF NOT EXISTS provider_payload_sha256 char(64),
  ADD COLUMN IF NOT EXISTS retry_count integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS failure_message varchar(240);

CREATE INDEX IF NOT EXISTS idx_saas_payments_pending_expiry
  ON saas_payments(expires_at) WHERE status IN ('CREATED','PENDING');

DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    GRANT UPDATE ON saas_payment_webhooks TO edusync_platform;
  END IF;
END $$;

INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,
  scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version)
VALUES ('subscription.payment.create','Abonnement EduSync','Abonnement','Payer l’abonnement de son école par Mobile Money',
  'create','HIGH','SERVER_ONLY',true,'["SCHOOL"]','OWNER_APPROVED','[]','[]',true,
  'École du jeton uniquement; paiement confirmé exclusivement par webhook signé.','3.0.0')
ON CONFLICT (code) DO UPDATE SET label=excluded.label,notes=excluded.notes,active=true,updated_at=now();

INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id,'subscription.payment.create' FROM rbac_roles r
WHERE r.level='SCHOOL' AND r.code IN ('ADMIN_SYSTEME_ECOLE','PROMOTEUR','GESTIONNAIRE','RESPONSABLE_FINANCE')
ON CONFLICT DO NOTHING;
