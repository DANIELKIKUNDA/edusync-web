-- External messaging industrialization (2026-10): e-mail (SMTP), SMS (Orange) and push (FCM) on the EXISTING
-- communications pipeline: Domain event -> transactional outbox -> worker -> notification policy -> delivery -> provider.
-- No second notification system: communication_messages / communication_deliveries stay the single source of truth.

-- 1. Messages: account / platform messages have no school (security e-mails, platform campaigns) ------------------
ALTER TABLE communication_messages ALTER COLUMN school_id DROP NOT NULL;
ALTER TABLE communication_messages ADD COLUMN IF NOT EXISTS channels text[] NOT NULL DEFAULT ARRAY['IN_APP']::text[];
ALTER TABLE communication_messages ADD COLUMN IF NOT EXISTS template_code varchar(96);
ALTER TABLE communication_messages ADD COLUMN IF NOT EXISTS link_path varchar(200);
ALTER TABLE communication_messages ADD COLUMN IF NOT EXISTS recipient_count integer NOT NULL DEFAULT 0;
ALTER TABLE communication_messages ADD COLUMN IF NOT EXISTS sms_segments_reserved integer NOT NULL DEFAULT 0 CHECK (sms_segments_reserved >= 0);
ALTER TABLE communication_messages ADD COLUMN IF NOT EXISTS dispatched_at timestamptz;
-- Idempotency of account / platform messages (the (school_id, idempotency_key) constraint ignores NULL schools).
CREATE UNIQUE INDEX IF NOT EXISTS uq_comm_message_account_key ON communication_messages(idempotency_key) WHERE school_id IS NULL;
DO $$ BEGIN
  ALTER TABLE communication_messages ADD CONSTRAINT communication_messages_scope_ck CHECK (school_id IS NOT NULL OR kind IN ('ACCOUNT','PLATFORM'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- 2. Recipient snapshot resolved by the use case (permission-aware, tenant-scoped) before the outbox event ------------
CREATE TABLE IF NOT EXISTS communication_recipients (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid REFERENCES schools(id) ON DELETE CASCADE,
  message_id uuid NOT NULL REFERENCES communication_messages(id) ON DELETE CASCADE,
  recipient_kind varchar(16) NOT NULL CHECK (recipient_kind IN ('GUARDIAN','USER')),
  recipient_ref uuid NOT NULL,
  user_id uuid REFERENCES users(id),
  phone_e164 varchar(20),
  email citext,
  display_name varchar(180),
  -- One-shot secret of this recipient (invitation / recovery link), AES-256-GCM, wiped once its deliveries are final.
  secret_ciphertext text,
  -- Platform messages (school_id NULL) addressed to a school user: push only reaches that user's devices of this school.
  target_school_id uuid REFERENCES schools(id) ON DELETE CASCADE,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (message_id, recipient_kind, recipient_ref)
);
ALTER TABLE communication_recipients ADD COLUMN IF NOT EXISTS secret_ciphertext text;
ALTER TABLE communication_recipients ADD COLUMN IF NOT EXISTS target_school_id uuid REFERENCES schools(id) ON DELETE CASCADE;

-- 3. Deliveries: canonical states, attempt tracking, encrypted one-shot secret payload -----------------------------
ALTER TABLE communication_deliveries ALTER COLUMN school_id DROP NOT NULL;
UPDATE communication_deliveries SET status='QUEUED' WHERE status='PENDING';
UPDATE communication_deliveries SET status='FAILED_PERMANENT' WHERE status='FAILED';
ALTER TABLE communication_deliveries ALTER COLUMN status SET DEFAULT 'QUEUED';
DO $$ BEGIN
  ALTER TABLE communication_deliveries ADD CONSTRAINT communication_deliveries_status_ck
    CHECK (status IN ('QUEUED','PROCESSING','SENT','DELIVERED','FAILED_RETRYABLE','FAILED_PERMANENT','CANCELLED'));
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  ALTER TABLE communication_deliveries ADD CONSTRAINT communication_deliveries_channel_ck CHECK (channel IN ('SMS','EMAIL','PUSH','IN_APP')) NOT VALID;
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
ALTER TABLE communication_deliveries ADD COLUMN IF NOT EXISTS recipient_id uuid REFERENCES communication_recipients(id) ON DELETE CASCADE;
ALTER TABLE communication_deliveries ADD COLUMN IF NOT EXISTS last_attempt_at timestamptz;
ALTER TABLE communication_deliveries ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;
ALTER TABLE communication_deliveries ADD COLUMN IF NOT EXISTS segments_billed integer CHECK (segments_billed IS NULL OR segments_billed >= 0);
-- SMS credits held for this delivery: RESERVED at confirmation, then CONSUMED (provider accepted) or RELEASED (failure/cancel).
ALTER TABLE communication_deliveries ADD COLUMN IF NOT EXISTS wallet_state varchar(12) CHECK (wallet_state IN ('RESERVED','CONSUMED','RELEASED'));
CREATE INDEX IF NOT EXISTS idx_comm_delivery_due_v2 ON communication_deliveries(status, next_attempt_at, created_at)
  WHERE status IN ('QUEUED','FAILED_RETRYABLE');
CREATE UNIQUE INDEX IF NOT EXISTS uq_comm_delivery_provider_message ON communication_deliveries(provider_code, provider_message_id)
  WHERE provider_message_id IS NOT NULL;

-- 4. School channel settings: push switch and SMS low-balance threshold (in billable SMS segments) ----------------
ALTER TABLE communication_settings ADD COLUMN IF NOT EXISTS push_enabled boolean NOT NULL DEFAULT true;
ALTER TABLE communication_settings ADD COLUMN IF NOT EXISTS sms_low_balance_threshold integer NOT NULL DEFAULT 50 CHECK (sms_low_balance_threshold >= 0);

-- 5. SMS wallet per school: balance + reservations, moved only through an append-only ledger ----------------------
CREATE TABLE IF NOT EXISTS school_sms_wallets (
  school_id uuid PRIMARY KEY REFERENCES schools(id) ON DELETE CASCADE,
  balance integer NOT NULL DEFAULT 0 CHECK (balance >= 0),
  reserved integer NOT NULL DEFAULT 0 CHECK (reserved >= 0),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version integer NOT NULL DEFAULT 1,
  CHECK (reserved <= balance)
);
CREATE TABLE IF NOT EXISTS school_sms_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
  movement_type varchar(16) NOT NULL CHECK (movement_type IN ('TOPUP','RESERVATION','CONSUMPTION','RELEASE','ADJUSTMENT','REFUND')),
  direction varchar(6) NOT NULL CHECK (direction IN ('CREDIT','DEBIT','HOLD','UNHOLD')),
  quantity integer NOT NULL CHECK (quantity > 0),
  balance_after integer NOT NULL CHECK (balance_after >= 0),
  reserved_after integer NOT NULL CHECK (reserved_after >= 0),
  source_type varchar(32),
  source_id uuid,
  actor_user_id uuid REFERENCES users(id),
  reference varchar(120),
  reason text,
  provider_message_id varchar(180),
  idempotency_key varchar(180) NOT NULL,
  -- Commercial data kept apart from school accounting: what the provider costs EduSync / what the school paid.
  provider_cost numeric(18,4),
  provider_cost_currency varchar(8),
  commercial_price numeric(18,4),
  commercial_currency varchar(8),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (school_id, idempotency_key),
  CHECK (movement_type <> 'ADJUSTMENT' OR length(trim(coalesce(reason,''))) >= 5),
  CHECK (movement_type <> 'TOPUP' OR length(trim(coalesce(reference,''))) >= 2)
);
CREATE INDEX IF NOT EXISTS idx_sms_ledger_school_created ON school_sms_ledger(school_id, created_at DESC, id DESC);

CREATE OR REPLACE FUNCTION school_sms_ledger_append_only() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN RAISE EXCEPTION 'school_sms_ledger est en ajout seul'; END $$;
DROP TRIGGER IF EXISTS trg_school_sms_ledger_append_only ON school_sms_ledger;
CREATE TRIGGER trg_school_sms_ledger_append_only BEFORE UPDATE OR DELETE ON school_sms_ledger
  FOR EACH ROW EXECUTE FUNCTION school_sms_ledger_append_only();

-- The only way to move SMS credits. Row lock on the wallet serializes concurrent movements of a school; the
-- idempotency key makes a retried movement (double click, worker retry) return the first ledger line unchanged.
-- Who may do what is enforced here, whatever the caller: schools reserve/release, workers consume/release,
-- the platform tops up / adjusts / refunds.
CREATE OR REPLACE FUNCTION school_sms_wallet_apply(
  p_school uuid, p_type text, p_quantity integer, p_key text, p_actor uuid DEFAULT NULL,
  p_source_type text DEFAULT NULL, p_source_id uuid DEFAULT NULL, p_reference text DEFAULT NULL, p_reason text DEFAULT NULL,
  p_provider_message_id text DEFAULT NULL, p_direction text DEFAULT NULL,
  p_provider_cost numeric DEFAULT NULL, p_provider_cost_currency text DEFAULT NULL,
  p_commercial_price numeric DEFAULT NULL, p_commercial_currency text DEFAULT NULL)
RETURNS school_sms_ledger LANGUAGE plpgsql AS $$
DECLARE
  w school_sms_wallets; existing school_sms_ledger; out_row school_sms_ledger;
  new_balance integer; new_reserved integer; dir text; held integer;
BEGIN
  IF p_quantity IS NULL OR p_quantity <= 0 THEN RAISE EXCEPTION 'SMS_QUANTITY_INVALID'; END IF;
  IF p_key IS NULL OR length(p_key) < 8 THEN RAISE EXCEPTION 'SMS_IDEMPOTENCY_KEY_REQUIRED'; END IF;
  IF current_user = 'edusync_tenant' AND p_type NOT IN ('RESERVATION','RELEASE') THEN RAISE EXCEPTION 'SMS_WALLET_FORBIDDEN'; END IF;
  IF current_user = 'edusync_worker' AND p_type NOT IN ('CONSUMPTION','RELEASE') THEN RAISE EXCEPTION 'SMS_WALLET_FORBIDDEN'; END IF;
  IF current_user = 'edusync_platform' AND p_type NOT IN ('TOPUP','ADJUSTMENT','REFUND') THEN RAISE EXCEPTION 'SMS_WALLET_FORBIDDEN'; END IF;
  INSERT INTO school_sms_wallets(school_id) VALUES (p_school) ON CONFLICT (school_id) DO NOTHING;
  SELECT * INTO w FROM school_sms_wallets WHERE school_id = p_school FOR UPDATE;
  IF NOT FOUND THEN RAISE EXCEPTION 'SMS_WALLET_NOT_FOUND'; END IF;
  SELECT * INTO existing FROM school_sms_ledger WHERE school_id = p_school AND idempotency_key = p_key;
  IF FOUND THEN RETURN existing; END IF;
  new_balance := w.balance; new_reserved := w.reserved;
  IF p_type = 'TOPUP' OR p_type = 'REFUND' THEN
    new_balance := w.balance + p_quantity; dir := 'CREDIT';
  ELSIF p_type = 'RESERVATION' THEN
    IF w.balance - w.reserved < p_quantity THEN RAISE EXCEPTION 'SMS_INSUFFICIENT_CREDIT'; END IF;
    new_reserved := w.reserved + p_quantity; dir := 'HOLD';
  ELSIF p_type = 'RELEASE' THEN
    IF w.reserved < p_quantity THEN RAISE EXCEPTION 'SMS_RELEASE_EXCEEDS_RESERVATION'; END IF;
    new_reserved := w.reserved - p_quantity; dir := 'UNHOLD';
  ELSIF p_type = 'CONSUMPTION' THEN
    -- Consumes the held credits first; a provider count higher than the estimate is taken from the free balance.
    held := least(p_quantity, w.reserved);
    IF w.balance - w.reserved < p_quantity - held THEN RAISE EXCEPTION 'SMS_INSUFFICIENT_CREDIT'; END IF;
    new_reserved := w.reserved - held; new_balance := w.balance - p_quantity; dir := 'DEBIT';
  ELSIF p_type = 'ADJUSTMENT' THEN
    IF p_direction = 'CREDIT' THEN new_balance := w.balance + p_quantity; dir := 'CREDIT';
    ELSIF p_direction = 'DEBIT' THEN
      IF w.balance - w.reserved < p_quantity THEN RAISE EXCEPTION 'SMS_INSUFFICIENT_CREDIT'; END IF;
      new_balance := w.balance - p_quantity; dir := 'DEBIT';
    ELSE RAISE EXCEPTION 'SMS_ADJUSTMENT_DIRECTION_REQUIRED'; END IF;
  ELSE RAISE EXCEPTION 'SMS_MOVEMENT_INVALID'; END IF;
  UPDATE school_sms_wallets SET balance = new_balance, reserved = new_reserved, updated_at = now(), version = version + 1
    WHERE school_id = p_school;
  INSERT INTO school_sms_ledger(school_id, movement_type, direction, quantity, balance_after, reserved_after, source_type, source_id,
      actor_user_id, reference, reason, provider_message_id, idempotency_key, provider_cost, provider_cost_currency,
      commercial_price, commercial_currency)
    VALUES (p_school, p_type, dir, p_quantity, new_balance, new_reserved, p_source_type, p_source_id, p_actor, p_reference, p_reason,
      p_provider_message_id, p_key, p_provider_cost, p_provider_cost_currency, p_commercial_price, p_commercial_currency)
    RETURNING * INTO out_row;
  RETURN out_row;
END $$;

-- 6. Push devices: FCM registration token encrypted at rest (hash for uniqueness), per device / membership --------
ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS token_ciphertext text;
ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS membership_id uuid REFERENCES school_memberships(id);
ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS device_id uuid;
ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS platform varchar(32);
ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS browser varchar(48);
ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS last_error_code varchar(64);
ALTER TABLE push_subscriptions ADD COLUMN IF NOT EXISTS last_error_at timestamptz;

-- 7. Account tokens (invitation, password recovery): only the SHA-256 of the token is stored --------------------
CREATE TABLE IF NOT EXISTS account_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose varchar(16) NOT NULL CHECK (purpose IN ('INVITATION','PASSWORD_RESET')),
  token_hash char(64) NOT NULL UNIQUE,
  school_id uuid REFERENCES schools(id) ON DELETE CASCADE,
  membership_id uuid REFERENCES school_memberships(id) ON DELETE CASCADE,
  created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  used_at timestamptz,
  revoked_at timestamptz,
  revoked_reason varchar(48),
  CHECK (expires_at > created_at)
);
CREATE INDEX IF NOT EXISTS idx_account_tokens_user_open ON account_tokens(user_id, purpose) WHERE used_at IS NULL AND revoked_at IS NULL;

-- 7b. Provider delivery receipts (Orange delivery-receipt callback): written by the API (webhook), applied by the worker.
-- Idempotent: the same receipt received twice is stored once.
CREATE TABLE IF NOT EXISTS provider_receipts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_code varchar(32) NOT NULL,
  provider_message_id varchar(180) NOT NULL,
  provider_status varchar(64) NOT NULL,
  status varchar(16) NOT NULL CHECK (status IN ('DELIVERED','FAILED','PENDING')),
  received_at timestamptz NOT NULL DEFAULT now(),
  applied_at timestamptz,
  UNIQUE (provider_code, provider_message_id, provider_status)
);
CREATE INDEX IF NOT EXISTS idx_provider_receipts_pending ON provider_receipts(received_at) WHERE applied_at IS NULL;

-- 8. Row-level security ----------------------------------------------------------------------------------------------
ALTER TABLE communication_recipients ENABLE ROW LEVEL SECURITY; ALTER TABLE communication_recipients FORCE ROW LEVEL SECURITY;
ALTER TABLE school_sms_wallets ENABLE ROW LEVEL SECURITY; ALTER TABLE school_sms_wallets FORCE ROW LEVEL SECURITY;
ALTER TABLE school_sms_ledger ENABLE ROW LEVEL SECURITY; ALTER TABLE school_sms_ledger FORCE ROW LEVEL SECURITY;
ALTER TABLE account_tokens ENABLE ROW LEVEL SECURITY; ALTER TABLE account_tokens FORCE ROW LEVEL SECURITY;
ALTER TABLE provider_receipts ENABLE ROW LEVEL SECURITY; ALTER TABLE provider_receipts FORCE ROW LEVEL SECURITY;
DO $$ DECLARE t text; BEGIN
  FOREACH t IN ARRAY ARRAY['communication_recipients','school_sms_wallets','school_sms_ledger'] LOOP
    EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
    EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (school_id=current_setting(''app.school_id'',true)::uuid) WITH CHECK (school_id=current_setting(''app.school_id'',true)::uuid)', t);
  END LOOP;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_worker') THEN
    FOREACH t IN ARRAY ARRAY['communication_recipients','school_sms_wallets','school_sms_ledger','communication_messages'] LOOP
      EXECUTE format('DROP POLICY IF EXISTS worker_queue ON %I', t);
      EXECUTE format('CREATE POLICY worker_queue ON %I TO edusync_worker USING (true) WITH CHECK (true)', t);
    END LOOP;
    DROP POLICY IF EXISTS worker_push ON push_subscriptions;
    CREATE POLICY worker_push ON push_subscriptions TO edusync_worker USING (true) WITH CHECK (true);
    GRANT SELECT, INSERT, UPDATE ON communication_recipients, communication_messages, communication_deliveries TO edusync_worker;
    GRANT SELECT, INSERT, UPDATE ON school_sms_wallets TO edusync_worker;
    GRANT SELECT, INSERT ON school_sms_ledger TO edusync_worker;
    GRANT SELECT, UPDATE ON push_subscriptions TO edusync_worker;
    GRANT SELECT (name) ON schools TO edusync_worker;      -- school name in e-mails / push titles (no other column)
    GRANT EXECUTE ON FUNCTION school_sms_wallet_apply(uuid,text,integer,text,uuid,text,uuid,text,text,text,text,numeric,text,numeric,text) TO edusync_worker;
    DROP POLICY IF EXISTS worker_queue ON provider_receipts;
    CREATE POLICY worker_queue ON provider_receipts TO edusync_worker USING (true) WITH CHECK (true);
    GRANT SELECT, UPDATE ON provider_receipts TO edusync_worker;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    -- Atelier Pro: wallets and operational metadata of every school; account / platform messages (school_id NULL).
    FOREACH t IN ARRAY ARRAY['school_sms_wallets','school_sms_ledger','account_tokens'] LOOP
      EXECUTE format('DROP POLICY IF EXISTS platform_all ON %I', t);
      EXECUTE format('CREATE POLICY platform_all ON %I TO edusync_platform USING (true) WITH CHECK (true)', t);
    END LOOP;
    FOREACH t IN ARRAY ARRAY['communication_messages','communication_deliveries','communication_recipients'] LOOP
      EXECUTE format('DROP POLICY IF EXISTS platform_account_messages ON %I', t);
      EXECUTE format('CREATE POLICY platform_account_messages ON %I TO edusync_platform USING (school_id IS NULL) WITH CHECK (school_id IS NULL)', t);
    END LOOP;
    -- Operational supervision reads delivery metadata of every school (never message bodies: see platform router).
    DROP POLICY IF EXISTS platform_delivery_metadata ON communication_deliveries;
    CREATE POLICY platform_delivery_metadata ON communication_deliveries FOR SELECT TO edusync_platform USING (true);
    DROP POLICY IF EXISTS platform_settings_read ON communication_settings;
    CREATE POLICY platform_settings_read ON communication_settings FOR SELECT TO edusync_platform USING (true);
    GRANT SELECT, INSERT, UPDATE ON school_sms_wallets, account_tokens TO edusync_platform;
    GRANT SELECT, INSERT ON school_sms_ledger TO edusync_platform;
    GRANT SELECT, INSERT ON communication_messages, communication_recipients TO edusync_platform;
    GRANT SELECT, INSERT ON communication_deliveries TO edusync_platform;
    GRANT SELECT ON communication_settings TO edusync_platform;
    DROP POLICY IF EXISTS platform_receipts ON provider_receipts;
    CREATE POLICY platform_receipts ON provider_receipts TO edusync_platform USING (true) WITH CHECK (true);
    GRANT SELECT, INSERT ON provider_receipts TO edusync_platform;
    GRANT EXECUTE ON FUNCTION school_sms_wallet_apply(uuid,text,integer,text,uuid,text,uuid,text,text,text,text,numeric,text,numeric,text) TO edusync_platform;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
    GRANT SELECT, INSERT ON communication_recipients TO edusync_tenant;
    GRANT SELECT, INSERT, UPDATE ON school_sms_wallets TO edusync_tenant;
    GRANT SELECT, INSERT ON school_sms_ledger TO edusync_tenant;
    GRANT EXECUTE ON FUNCTION school_sms_wallet_apply(uuid,text,integer,text,uuid,text,uuid,text,text,text,text,numeric,text,numeric,text) TO edusync_tenant;
  END IF;
END $$;
REVOKE UPDATE, DELETE ON school_sms_ledger FROM PUBLIC;
REVOKE DELETE ON communication_recipients, school_sms_wallets, account_tokens FROM PUBLIC;

-- 9. Atelier Pro capabilities (no reading of school message bodies) -------------------------------------------------
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,registry_version) VALUES
 ('platform.messaging.read','Atelier Pro','Messagerie','Voir l’état des fournisseurs, portefeuilles SMS et volumes d’envoi (sans le contenu des messages)','read','MEDIUM','SERVER_ONLY',false,'["PLATFORM"]'::jsonb,'NEW_APPROVED','0.76.0'),
 ('platform.sms_wallet.credit','Atelier Pro','Messagerie','Créditer ou ajuster le portefeuille SMS d’une école','credit','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','0.76.0')
ON CONFLICT(code) DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,c.code FROM rbac_roles r JOIN capability_catalog c ON c.code IN ('platform.messaging.read','platform.sms_wallet.credit')
WHERE r.code='MANAGER_SYSTEME' AND r.kind='PLATFORM_STANDARD'
ON CONFLICT DO NOTHING;
