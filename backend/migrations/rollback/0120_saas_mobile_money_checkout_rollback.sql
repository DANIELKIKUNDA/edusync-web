DELETE FROM rbac_role_capabilities WHERE capability_code='subscription.payment.create';
DELETE FROM capability_catalog WHERE code='subscription.payment.create';
REVOKE UPDATE ON saas_payment_webhooks FROM edusync_platform;
DROP INDEX IF EXISTS idx_saas_payments_pending_expiry;
ALTER TABLE saas_payments DROP COLUMN IF EXISTS failure_message, DROP COLUMN IF EXISTS retry_count,
 DROP COLUMN IF EXISTS provider_payload_sha256, DROP COLUMN IF EXISTS last_provider_update_at,
 DROP COLUMN IF EXISTS expires_at;
