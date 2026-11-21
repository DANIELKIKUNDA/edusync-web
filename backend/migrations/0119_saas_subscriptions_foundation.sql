-- EduSync V1.0-SaaS S1: commercial subscriptions. This is NOT school fee billing.
-- Platform-owned tables only in S1; the school self-service projection is introduced in S3.

CREATE TABLE IF NOT EXISTS saas_modules (
  code varchar(64) PRIMARY KEY,
  label varchar(160) NOT NULL,
  description text NOT NULL DEFAULT '',
  status varchar(16) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  dependencies jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(dependencies)='array'),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS saas_plans (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  code varchar(64) NOT NULL UNIQUE,
  name varchar(160) NOT NULL,
  description text NOT NULL DEFAULT '',
  status varchar(16) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  public_offer boolean NOT NULL DEFAULT true,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS saas_plan_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id uuid NOT NULL REFERENCES saas_plans(id),
  version integer NOT NULL CHECK (version > 0),
  billing_cycle varchar(16) NOT NULL CHECK (billing_cycle IN ('MONTHLY','QUARTERLY','ANNUAL')),
  currency varchar(3) NOT NULL CHECK (currency IN ('USD','CDF')),
  amount numeric(18,2) NOT NULL CHECK (amount >= 0),
  trial_days smallint NOT NULL DEFAULT 0 CHECK (trial_days BETWEEN 0 AND 90),
  grace_days smallint NOT NULL DEFAULT 10 CHECK (grace_days BETWEEN 0 AND 90),
  effective_from date NOT NULL,
  effective_until date,
  status varchar(16) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','PUBLISHED','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(plan_id, version, billing_cycle, currency),
  CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE TABLE IF NOT EXISTS saas_plan_modules (
  plan_version_id uuid NOT NULL REFERENCES saas_plan_versions(id) ON DELETE CASCADE,
  module_code varchar(64) NOT NULL REFERENCES saas_modules(code),
  limits jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(limits)='object'),
  PRIMARY KEY(plan_version_id, module_code)
);

CREATE TABLE IF NOT EXISTS saas_subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  plan_version_id uuid NOT NULL REFERENCES saas_plan_versions(id),
  billing_cycle varchar(16) NOT NULL CHECK (billing_cycle IN ('MONTHLY','QUARTERLY','ANNUAL')),
  status varchar(24) NOT NULL CHECK (status IN ('TRIAL','PENDING_PAYMENT','ACTIVE','PAST_DUE','GRACE','LIMITED','SUSPENDED','CANCELLED','EXPIRED')),
  current_period_start date NOT NULL,
  current_period_end date NOT NULL,
  next_billing_on date,
  grace_days smallint NOT NULL DEFAULT 10 CHECK (grace_days BETWEEN 0 AND 90),
  auto_renew boolean NOT NULL DEFAULT true,
  cancelled_at timestamptz,
  cancellation_reason text,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (current_period_end > current_period_start),
  CHECK ((status='CANCELLED') = (cancelled_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_saas_school_current_subscription ON saas_subscriptions(school_id)
  WHERE status NOT IN ('CANCELLED','EXPIRED');
CREATE INDEX IF NOT EXISTS idx_saas_subscriptions_due ON saas_subscriptions(status,next_billing_on);

CREATE TABLE IF NOT EXISTS saas_subscription_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  subscription_id uuid NOT NULL REFERENCES saas_subscriptions(id),
  school_id uuid NOT NULL REFERENCES schools(id),
  actor_user_id uuid REFERENCES users(id),
  from_status varchar(24),
  to_status varchar(24) NOT NULL,
  reason text NOT NULL CHECK (length(btrim(reason)) >= 5),
  correlation_id uuid,
  idempotency_key varchar(180),
  occurred_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_saas_subscription_event_idempotency
  ON saas_subscription_events(subscription_id,idempotency_key) WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS saas_entitlements (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  subscription_id uuid REFERENCES saas_subscriptions(id),
  module_code varchar(64) NOT NULL REFERENCES saas_modules(code),
  source varchar(16) NOT NULL CHECK (source IN ('PLAN','ADDON','TRIAL','MANUAL','MIGRATION')),
  status varchar(16) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','EXPIRED','REVOKED')),
  starts_at timestamptz NOT NULL DEFAULT now(),
  ends_at timestamptz,
  limits jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(limits)='object'),
  reason text,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (ends_at IS NULL OR ends_at > starts_at)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_saas_active_entitlement ON saas_entitlements(school_id,module_code)
  WHERE status='ACTIVE';

CREATE SEQUENCE IF NOT EXISTS saas_invoice_number_seq START 1;
CREATE TABLE IF NOT EXISTS saas_invoices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_number varchar(40) NOT NULL UNIQUE,
  school_id uuid NOT NULL REFERENCES schools(id),
  subscription_id uuid REFERENCES saas_subscriptions(id),
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ISSUED','PARTIALLY_PAID','PAID','OVERDUE','VOID','REFUNDED')),
  currency varchar(3) NOT NULL CHECK (currency IN ('USD','CDF')),
  period_start date NOT NULL,
  period_end date NOT NULL,
  issued_at timestamptz,
  due_at timestamptz,
  subtotal numeric(18,2) NOT NULL CHECK (subtotal >= 0),
  discount_total numeric(18,2) NOT NULL DEFAULT 0 CHECK (discount_total >= 0),
  fee_total numeric(18,2) NOT NULL DEFAULT 0 CHECK (fee_total >= 0),
  total numeric(18,2) NOT NULL CHECK (total >= 0),
  paid_total numeric(18,2) NOT NULL DEFAULT 0 CHECK (paid_total >= 0),
  bill_to_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(bill_to_snapshot)='object'),
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (period_end > period_start),
  CHECK (paid_total <= total),
  CHECK (total = subtotal - discount_total + fee_total),
  CHECK ((status='DRAFT') OR (issued_at IS NOT NULL AND due_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_saas_invoices_school_due ON saas_invoices(school_id,due_at DESC);
CREATE INDEX IF NOT EXISTS idx_saas_invoices_collection ON saas_invoices(status,due_at);

CREATE TABLE IF NOT EXISTS saas_invoice_lines (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  invoice_id uuid NOT NULL REFERENCES saas_invoices(id) ON DELETE CASCADE,
  module_code varchar(64) REFERENCES saas_modules(code),
  description varchar(300) NOT NULL,
  quantity numeric(12,2) NOT NULL DEFAULT 1 CHECK (quantity > 0),
  unit_price numeric(18,2) NOT NULL CHECK (unit_price >= 0),
  line_total numeric(18,2) NOT NULL CHECK (line_total >= 0),
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata)='object'),
  CHECK (line_total = quantity * unit_price)
);

CREATE TABLE IF NOT EXISTS saas_payments (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payment_reference varchar(64) NOT NULL UNIQUE,
  invoice_id uuid NOT NULL REFERENCES saas_invoices(id),
  school_id uuid NOT NULL REFERENCES schools(id),
  provider varchar(48) NOT NULL,
  provider_reference varchar(180),
  channel varchar(24) NOT NULL CHECK (channel IN ('MANUAL','MOBILE_MONEY','CARD','BANK_TRANSFER','PAYMENT_LINK')),
  status varchar(16) NOT NULL CHECK (status IN ('CREATED','PENDING','SUCCEEDED','FAILED','CANCELLED','EXPIRED','REFUNDED')),
  currency varchar(3) NOT NULL CHECK (currency IN ('USD','CDF')),
  amount numeric(18,2) NOT NULL CHECK (amount > 0),
  payer_phone_masked varchar(32),
  failure_code varchar(80),
  initiated_at timestamptz NOT NULL DEFAULT now(),
  confirmed_at timestamptz,
  version bigint NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(provider,provider_reference),
  CHECK ((status IN ('SUCCEEDED','REFUNDED')) = (confirmed_at IS NOT NULL))
);
CREATE INDEX IF NOT EXISTS idx_saas_payments_invoice ON saas_payments(invoice_id,created_at DESC);

CREATE TABLE IF NOT EXISTS saas_payment_webhooks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider varchar(48) NOT NULL,
  provider_event_id varchar(180) NOT NULL,
  signature_verified boolean NOT NULL,
  body_sha256 varchar(64) NOT NULL CHECK (body_sha256 ~ '^[0-9a-f]{64}$'),
  processing_status varchar(16) NOT NULL CHECK (processing_status IN ('RECEIVED','PROCESSED','REJECTED','FAILED')),
  error_code varchar(80),
  received_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  UNIQUE(provider,provider_event_id)
);

-- Commercial capabilities: only the platform manager receives them in S1.
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version)
VALUES
 ('platform.billing.read','Atelier Pro','Abonnements','Consulter les abonnements','read','HIGH','SERVER_ONLY',false,'["PLATFORM"]','NEW_APPROVED','[]','[]',true,'Données commerciales Volcano Tech','3.0.0'),
 ('platform.billing.plans.manage','Atelier Pro','Abonnements','Gérer les plans tarifaires','manage','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]','NEW_APPROVED','[]','[]',true,'MFA récente requise','3.0.0'),
 ('platform.billing.subscriptions.manage','Atelier Pro','Abonnements','Gérer les abonnements','manage','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]','NEW_APPROVED','[]','[]',true,'MFA récente requise','3.0.0'),
 ('platform.billing.invoices.manage','Atelier Pro','Abonnements','Gérer les factures commerciales','manage','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]','NEW_APPROVED','[]','[]',true,'MFA récente requise','3.0.0'),
 ('platform.billing.payments.reconcile','Atelier Pro','Abonnements','Rapprocher les paiements','reconcile','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]','NEW_APPROVED','[]','[]',true,'MFA récente requise','3.0.0'),
 ('platform.billing.overrides.grant','Atelier Pro','Abonnements','Accorder une grâce ou remise','grant','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]','NEW_APPROVED','[]','[]',true,'MFA et motif obligatoires','3.0.0'),
 ('platform.billing.export','Atelier Pro','Abonnements','Exporter les données commerciales','export','HIGH','SERVER_ONLY',true,'["PLATFORM"]','NEW_APPROVED','[]','["CSV","XLSX"]',true,'Export audité','3.0.0')
ON CONFLICT (code) DO UPDATE SET label=EXCLUDED.label, risk=EXCLUDED.risk, audit_required=EXCLUDED.audit_required,
  notes=EXCLUDED.notes, registry_version=EXCLUDED.registry_version, active=true, updated_at=now();

INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,c.code FROM rbac_roles r CROSS JOIN capability_catalog c
WHERE r.code='MANAGER_SYSTEME' AND r.level='PLATFORM' AND c.code LIKE 'platform.billing.%'
ON CONFLICT DO NOTHING;

-- Initial module catalogue. Future functionality remains DRAFT and cannot be sold.
INSERT INTO saas_modules(code,label,status,dependencies) VALUES
 ('CORE_SCHOOL','Socle école','ACTIVE','[]'),
 ('FINANCE','Finance scolaire','ACTIVE','["CORE_SCHOOL"]'),
 ('ENROLLMENT','Inscriptions et élèves','ACTIVE','["CORE_SCHOOL"]'),
 ('RECOVERY','Recouvrement','ACTIVE','["FINANCE"]'),
 ('REPORTS','Rapports','ACTIVE','["FINANCE"]'),
 ('PERSONNEL','Personnel','ACTIVE','["CORE_SCHOOL"]'),
 ('DOCUMENTS','Documents','ACTIVE','["CORE_SCHOOL"]'),
 ('COMMUNICATIONS','Communication','ACTIVE','["CORE_SCHOOL"]'),
 ('ACADEMIC','Gestion académique','DRAFT','["CORE_SCHOOL"]'),
 ('GRADES','Notes et cotation','DRAFT','["ACADEMIC"]'),
 ('REPORT_CARDS','Bulletins','DRAFT','["GRADES"]'),
 ('PARENT_PORTAL','Portail parent','DRAFT','["CORE_SCHOOL"]'),
 ('ADVANCED_ANALYTICS','Analyses avancées','DRAFT','["CORE_SCHOOL"]'),
 ('MULTI_SCHOOL','Pilotage multi-écoles','DRAFT','["CORE_SCHOOL"]')
ON CONFLICT (code) DO NOTHING;

REVOKE ALL ON saas_modules,saas_plans,saas_plan_versions,saas_plan_modules,saas_subscriptions,
  saas_subscription_events,saas_entitlements,saas_invoices,saas_invoice_lines,saas_payments,
  saas_payment_webhooks FROM PUBLIC;
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    GRANT SELECT,INSERT,UPDATE,DELETE ON saas_modules,saas_plans,saas_plan_versions,saas_plan_modules,
      saas_subscriptions,saas_entitlements,saas_invoice_lines TO edusync_platform;
    GRANT SELECT,INSERT ON saas_subscription_events,saas_payment_webhooks TO edusync_platform;
    GRANT SELECT,INSERT,UPDATE ON saas_invoices,saas_payments TO edusync_platform;
    GRANT USAGE,SELECT ON SEQUENCE saas_invoice_number_seq TO edusync_platform;
  END IF;
END $$;

