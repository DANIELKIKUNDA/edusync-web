DELETE FROM rbac_role_capabilities WHERE capability_code LIKE 'platform.billing.%';
DELETE FROM capability_catalog WHERE code LIKE 'platform.billing.%';
DROP TABLE IF EXISTS saas_payment_webhooks;
DROP TABLE IF EXISTS saas_payments;
DROP TABLE IF EXISTS saas_invoice_lines;
DROP TABLE IF EXISTS saas_invoices;
DROP SEQUENCE IF EXISTS saas_invoice_number_seq;
DROP TABLE IF EXISTS saas_entitlements;
DROP TABLE IF EXISTS saas_subscription_events;
DROP TABLE IF EXISTS saas_subscriptions;
DROP TABLE IF EXISTS saas_plan_modules;
DROP TABLE IF EXISTS saas_plan_versions;
DROP TABLE IF EXISTS saas_plans;
DROP TABLE IF EXISTS saas_modules;

