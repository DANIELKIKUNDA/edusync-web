-- EduSync WEB-0D — protocole d'encaissement CASH offline définitif, single-writer par école.
-- But: permettre un reçu officiel hors connexion sans double encaissement silencieux.
-- Doctrine de sécurité:
--  * un seul lease financier offline PREPARING/ACTIVE/DRAINING par école;
--  * le serveur NE libère JAMAIS automatiquement le lease à l'expiration locale;
--  * pendant ce lease, toutes les autres écritures Finance devront être bloquées par l'adapter Finance;
--  * un appareil s'arrête localement à local_stop_at, puis ne fait que synchroniser/drainer;
--  * reçus préalloués uniques, journal hash-chain, exact-once operation_id/idempotency_key;
--  * v1 offline définitif = CASH uniquement, charges existantes figées, aucune remise/tarif/remboursement offline.

CREATE TABLE IF NOT EXISTS offline_finance_leases (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  cashier_user_id uuid NOT NULL REFERENCES users(id),
  device_id uuid NOT NULL REFERENCES devices(id),
  cash_session_id uuid NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'PREPARING'
    CHECK (status IN ('PREPARING','ACTIVE','DRAINING','CLOSED','FORCE_RELEASED')),
  local_stop_at timestamptz NOT NULL,
  max_payments integer NOT NULL CHECK (max_payments > 0),
  max_cdf numeric(18,2) NOT NULL DEFAULT 0 CHECK (max_cdf >= 0),
  max_usd numeric(18,2) NOT NULL DEFAULT 0 CHECK (max_usd >= 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  activated_at timestamptz,
  draining_at timestamptz,
  closed_at timestamptz,
  reconciled_count integer,
  reconciled_cdf numeric(18,2),
  reconciled_usd numeric(18,2),
  final_entry_hash char(64),
  force_released_at timestamptz,
  force_released_by uuid REFERENCES users(id),
  force_release_reason text,
  CHECK ((status <> 'FORCE_RELEASED') OR (force_released_at IS NOT NULL AND force_released_by IS NOT NULL AND length(trim(force_release_reason)) >= 10))
);

-- Un lease en préparation est déjà exclusif: aucune fenêtre de course entre snapshot et activation.
CREATE UNIQUE INDEX IF NOT EXISTS uq_offline_finance_one_writer_per_school
  ON offline_finance_leases(school_id)
  WHERE status IN ('PREPARING','ACTIVE','DRAINING');
CREATE INDEX IF NOT EXISTS idx_offline_finance_lease_device
  ON offline_finance_leases(school_id,device_id,status);

CREATE TABLE IF NOT EXISTS offline_receipt_counters (
  school_id uuid PRIMARY KEY REFERENCES schools(id),
  last_value bigint NOT NULL DEFAULT 0 CHECK (last_value >= 0),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION next_offline_receipt_no(p_school_id uuid)
RETURNS text LANGUAGE plpgsql AS $$
DECLARE
  v_counter bigint;
  v_code text;
BEGIN
  INSERT INTO offline_receipt_counters(school_id,last_value)
  VALUES(p_school_id,1)
  ON CONFLICT (school_id) DO UPDATE
     SET last_value=offline_receipt_counters.last_value+1,updated_at=now()
  RETURNING last_value INTO v_counter;
  SELECT code INTO v_code FROM schools WHERE id=p_school_id;
  IF v_code IS NULL THEN RAISE EXCEPTION 'school_not_found'; END IF;
  RETURN 'OFF-' || upper(v_code) || '-' || to_char(current_date,'YYYY') || '-' || lpad(v_counter::text,8,'0');
END;
$$;

CREATE TABLE IF NOT EXISTS offline_receipt_tokens (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  lease_id uuid NOT NULL REFERENCES offline_finance_leases(id) ON DELETE RESTRICT,
  receipt_no varchar(96) NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'AVAILABLE' CHECK(status IN ('AVAILABLE','CONSUMED','VOID')),
  created_at timestamptz NOT NULL DEFAULT now(),
  consumed_by_operation_id uuid,
  consumed_at timestamptz,
  void_reason text,
  UNIQUE(school_id,receipt_no),
  UNIQUE(lease_id,id),
  CHECK ((status <> 'CONSUMED') OR (consumed_by_operation_id IS NOT NULL AND consumed_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_offline_receipt_consumed_operation
  ON offline_receipt_tokens(school_id,consumed_by_operation_id)
  WHERE consumed_by_operation_id IS NOT NULL;

-- Snapshot des seules obligations que l'appareil a le droit de solder hors ligne.
-- Les UUID pointent vers le futur Finance/Scolarité Web et restent intentionnellement sans FK en WEB-0D.
CREATE TABLE IF NOT EXISTS offline_charge_snapshots (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  lease_id uuid NOT NULL REFERENCES offline_finance_leases(id) ON DELETE RESTRICT,
  charge_id uuid NOT NULL,
  enrollment_id uuid NOT NULL,
  student_id uuid NOT NULL,
  currency varchar(3) NOT NULL CHECK(currency IN ('CDF','USD')),
  remaining_amount numeric(18,2) NOT NULL CHECK(remaining_amount >= 0),
  charge_version bigint NOT NULL CHECK(charge_version >= 1),
  snapshotted_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(lease_id,charge_id)
);
CREATE INDEX IF NOT EXISTS idx_offline_snapshots_student
  ON offline_charge_snapshots(lease_id,student_id,enrollment_id);

CREATE TABLE IF NOT EXISTS offline_payment_inbox (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  lease_id uuid NOT NULL REFERENCES offline_finance_leases(id) ON DELETE RESTRICT,
  operation_id uuid NOT NULL,
  idempotency_key varchar(180) NOT NULL,
  device_id uuid NOT NULL REFERENCES devices(id),
  cashier_user_id uuid NOT NULL REFERENCES users(id),
  cash_session_id uuid NOT NULL,
  receipt_token_id uuid NOT NULL REFERENCES offline_receipt_tokens(id),
  receipt_no varchar(96) NOT NULL,
  student_id uuid NOT NULL,
  enrollment_id uuid NOT NULL,
  currency varchar(3) NOT NULL CHECK(currency IN ('CDF','USD')),
  amount numeric(18,2) NOT NULL CHECK(amount > 0),
  mode varchar(16) NOT NULL CHECK(mode='CASH'),
  journal_seq integer NOT NULL CHECK(journal_seq >= 1),
  payload jsonb NOT NULL,
  previous_entry_hash char(64),
  entry_hash char(64) NOT NULL,
  client_time timestamptz NOT NULL,
  received_at timestamptz NOT NULL DEFAULT now(),
  processed_at timestamptz,
  status varchar(24) NOT NULL DEFAULT 'RECEIVED' CHECK(status IN ('RECEIVED','APPLIED','REJECTED')),
  payment_id uuid,
  rejection_code varchar(96),
  UNIQUE(school_id,operation_id),
  UNIQUE(school_id,idempotency_key),
  UNIQUE(school_id,receipt_no),
  UNIQUE(school_id,entry_hash),
  UNIQUE(lease_id,journal_seq)
);
CREATE INDEX IF NOT EXISTS idx_offline_payment_lease_status
  ON offline_payment_inbox(lease_id,status,client_time,operation_id);

-- Cohérence school_id entre enfant et parent de protocole (défense en profondeur).
CREATE OR REPLACE FUNCTION enforce_offline_finance_scope() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_school uuid;
BEGIN
  SELECT school_id INTO v_school FROM offline_finance_leases WHERE id=NEW.lease_id;
  IF v_school IS NULL OR v_school <> NEW.school_id THEN
    RAISE EXCEPTION 'offline_finance_cross_tenant_scope';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_receipt_scope ON offline_receipt_tokens;
CREATE TRIGGER trg_offline_receipt_scope BEFORE INSERT OR UPDATE ON offline_receipt_tokens
FOR EACH ROW EXECUTE FUNCTION enforce_offline_finance_scope();
DROP TRIGGER IF EXISTS trg_offline_snapshot_scope ON offline_charge_snapshots;
CREATE TRIGGER trg_offline_snapshot_scope BEFORE INSERT OR UPDATE ON offline_charge_snapshots
FOR EACH ROW EXECUTE FUNCTION enforce_offline_finance_scope();
DROP TRIGGER IF EXISTS trg_offline_inbox_scope ON offline_payment_inbox;
CREATE TRIGGER trg_offline_inbox_scope BEFORE INSERT OR UPDATE ON offline_payment_inbox
FOR EACH ROW EXECUTE FUNCTION enforce_offline_finance_scope();

-- RLS strict pour tous les artefacts offline tenant.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY[
    'offline_finance_leases','offline_receipt_counters','offline_receipt_tokens',
    'offline_charge_snapshots','offline_payment_inbox'
  ] LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY',t);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY',t);
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I',t || '_tenant',t);
    EXECUTE format(
      'CREATE POLICY %I ON %I FOR ALL TO edusync_tenant USING (school_id = nullif(current_setting(''app.current_school_id'',true),'''')::uuid) WITH CHECK (school_id = nullif(current_setting(''app.current_school_id'',true),'''')::uuid)',
      t || '_tenant',t
    );
    EXECUTE format('DROP POLICY IF EXISTS %I ON %I',t || '_platform',t);
    EXECUTE format('CREATE POLICY %I ON %I FOR ALL TO edusync_platform USING (true) WITH CHECK (true)',t || '_platform',t);
  END LOOP;
END $$;

-- Permission explicite: encaisser en ligne ne donne pas automatiquement le droit d'armer une caisse offline.
INSERT INTO permissions(code,label) VALUES
 ('finance.offline.arm','Armer une caisse pour encaissement offline'),
 ('finance.offline.reconcile','Synchroniser et rapprocher une caisse offline'),
 ('finance.offline.force_release','Libérer de force une caisse offline après incident')
ON CONFLICT(code) DO NOTHING;

INSERT INTO role_permissions(role_id,permission_id)
SELECT r.id,p.id FROM roles r JOIN permissions p ON (
  (r.code='SCHOOL_ADMIN') OR
  (r.code='CAISSIER' AND p.code IN ('finance.offline.arm','finance.offline.reconcile'))
)
ON CONFLICT DO NOTHING;

-- Toute future écriture Finance Web DOIT appeler cette fonction avant de muter le ledger.
-- Si un lease existe, seul son appareil/cashier/session peut écrire en fournissant le lease id.
CREATE OR REPLACE FUNCTION assert_finance_writer_allowed(
  p_school_id uuid,
  p_user_id uuid,
  p_device_id uuid,
  p_cash_session_id uuid,
  p_lease_id uuid DEFAULT NULL
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE l offline_finance_leases%ROWTYPE;
BEGIN
  SELECT * INTO l FROM offline_finance_leases
   WHERE school_id=p_school_id AND status IN ('PREPARING','ACTIVE','DRAINING')
   ORDER BY created_at DESC LIMIT 1 FOR UPDATE;
  IF NOT FOUND THEN RETURN; END IF;
  IF p_lease_id IS NULL OR l.id<>p_lease_id OR l.cashier_user_id<>p_user_id
     OR l.device_id<>p_device_id OR l.cash_session_id<>p_cash_session_id THEN
    RAISE EXCEPTION 'finance_locked_by_offline_lease';
  END IF;
  IF l.status='PREPARING' THEN
    RAISE EXCEPTION 'offline_lease_not_active';
  END IF;
END;
$$;

-- ---------------------------------------------------------------------------
-- Invariants de mutation: une fois armées, les preuves financières ne sont pas réécrites.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION protect_offline_lease_transition() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='UPDATE' THEN
    IF OLD.school_id<>NEW.school_id OR OLD.cashier_user_id<>NEW.cashier_user_id
       OR OLD.device_id<>NEW.device_id OR OLD.cash_session_id<>NEW.cash_session_id
       OR OLD.max_payments<>NEW.max_payments OR OLD.max_cdf<>NEW.max_cdf OR OLD.max_usd<>NEW.max_usd
       OR OLD.local_stop_at<>NEW.local_stop_at THEN
      RAISE EXCEPTION 'offline_lease_identity_or_limits_immutable';
    END IF;
    IF OLD.status='PREPARING' AND NEW.status NOT IN ('PREPARING','ACTIVE','FORCE_RELEASED') THEN
      RAISE EXCEPTION 'offline_lease_invalid_transition';
    ELSIF OLD.status='ACTIVE' AND NEW.status NOT IN ('ACTIVE','DRAINING','CLOSED','FORCE_RELEASED') THEN
      RAISE EXCEPTION 'offline_lease_invalid_transition';
    ELSIF OLD.status='DRAINING' AND NEW.status NOT IN ('DRAINING','CLOSED','FORCE_RELEASED') THEN
      RAISE EXCEPTION 'offline_lease_invalid_transition';
    ELSIF OLD.status IN ('CLOSED','FORCE_RELEASED') AND NEW.status<>OLD.status THEN
      RAISE EXCEPTION 'offline_lease_terminal';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_lease_transition ON offline_finance_leases;
CREATE TRIGGER trg_offline_lease_transition BEFORE UPDATE ON offline_finance_leases
FOR EACH ROW EXECUTE FUNCTION protect_offline_lease_transition();

CREATE OR REPLACE FUNCTION protect_offline_snapshot_mutation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_status text;
BEGIN
  SELECT status INTO v_status FROM offline_finance_leases WHERE id=(CASE WHEN TG_OP='DELETE' THEN OLD.lease_id ELSE NEW.lease_id END);
  IF TG_OP='DELETE' THEN
    IF v_status<>'PREPARING' THEN RAISE EXCEPTION 'offline_snapshot_frozen'; END IF;
    RETURN OLD;
  END IF;
  IF TG_OP='UPDATE' AND v_status<>'PREPARING' THEN
    RAISE EXCEPTION 'offline_snapshot_frozen';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_snapshot_freeze ON offline_charge_snapshots;
CREATE TRIGGER trg_offline_snapshot_freeze BEFORE UPDATE OR DELETE ON offline_charge_snapshots
FOR EACH ROW EXECUTE FUNCTION protect_offline_snapshot_mutation();

CREATE OR REPLACE FUNCTION protect_offline_receipt_token() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'offline_receipt_token_delete_forbidden'; END IF;
  IF OLD.school_id<>NEW.school_id OR OLD.lease_id<>NEW.lease_id OR OLD.receipt_no<>NEW.receipt_no THEN
    RAISE EXCEPTION 'offline_receipt_token_identity_immutable';
  END IF;
  IF OLD.status='AVAILABLE' AND NEW.status NOT IN ('AVAILABLE','CONSUMED','VOID') THEN
    RAISE EXCEPTION 'offline_receipt_invalid_transition';
  ELSIF OLD.status IN ('CONSUMED','VOID') AND NEW.status<>OLD.status THEN
    RAISE EXCEPTION 'offline_receipt_terminal';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_receipt_protect ON offline_receipt_tokens;
CREATE TRIGGER trg_offline_receipt_protect BEFORE UPDATE OR DELETE ON offline_receipt_tokens
FOR EACH ROW EXECUTE FUNCTION protect_offline_receipt_token();

CREATE OR REPLACE FUNCTION protect_offline_payment_inbox() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'offline_payment_protocol_delete_forbidden'; END IF;
  IF OLD.school_id<>NEW.school_id OR OLD.lease_id<>NEW.lease_id OR OLD.operation_id<>NEW.operation_id
     OR OLD.idempotency_key<>NEW.idempotency_key OR OLD.device_id<>NEW.device_id
     OR OLD.cashier_user_id<>NEW.cashier_user_id OR OLD.cash_session_id<>NEW.cash_session_id
     OR OLD.receipt_token_id<>NEW.receipt_token_id OR OLD.receipt_no<>NEW.receipt_no
     OR OLD.student_id<>NEW.student_id OR OLD.enrollment_id<>NEW.enrollment_id
     OR OLD.currency<>NEW.currency OR OLD.amount<>NEW.amount OR OLD.mode<>NEW.mode
     OR OLD.journal_seq<>NEW.journal_seq OR OLD.payload<>NEW.payload
     OR OLD.previous_entry_hash IS DISTINCT FROM NEW.previous_entry_hash
     OR OLD.entry_hash<>NEW.entry_hash OR OLD.client_time<>NEW.client_time THEN
    RAISE EXCEPTION 'offline_payment_protocol_immutable_fields';
  END IF;
  IF OLD.status IN ('APPLIED','REJECTED') AND NEW.status<>OLD.status THEN
    RAISE EXCEPTION 'offline_payment_protocol_terminal';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_payment_protect ON offline_payment_inbox;
CREATE TRIGGER trg_offline_payment_protect BEFORE UPDATE OR DELETE ON offline_payment_inbox
FOR EACH ROW EXECUTE FUNCTION protect_offline_payment_inbox();

-- Audit automatique des transitions du lease. L'audit global reste append-only.
CREATE OR REPLACE FUNCTION audit_offline_lease_transition() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE v_action text;
DECLARE v_actor uuid;
BEGIN
  IF TG_OP='INSERT' THEN
    v_action := 'OFFLINE_FINANCE_LEASE_PREPARING';
  ELSIF NEW.status=OLD.status THEN
    RETURN NEW;
  ELSE
    v_action := 'OFFLINE_FINANCE_LEASE_' || NEW.status;
  END IF;
  v_actor := COALESCE(NULLIF(current_setting('app.current_user_id',true),'')::uuid, NEW.force_released_by, NEW.cashier_user_id);
  INSERT INTO audit_events(
    school_id,actor_user_id,action,entity_type,entity_id,source,result,device_id,new_json,reason
  ) VALUES(
    NEW.school_id,v_actor,v_action,'OFFLINE_FINANCE_LEASE',NEW.id,'WEB','SUCCESS',NEW.device_id,
    jsonb_build_object('status',NEW.status,'cashSessionId',NEW.cash_session_id,'localStopAt',NEW.local_stop_at,
                       'maxPayments',NEW.max_payments,'maxCDF',NEW.max_cdf,'maxUSD',NEW.max_usd),
    NEW.force_release_reason
  );
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_lease_audit ON offline_finance_leases;
CREATE TRIGGER trg_offline_lease_audit AFTER INSERT OR UPDATE OF status ON offline_finance_leases
FOR EACH ROW EXECUTE FUNCTION audit_offline_lease_transition();

CREATE OR REPLACE FUNCTION audit_offline_payment_applied() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IS DISTINCT FROM NEW.status AND NEW.status='APPLIED' THEN
    INSERT INTO audit_events(
      school_id,actor_user_id,action,entity_type,entity_id,source,result,device_id,idempotency_key,new_json
    ) VALUES(
      NEW.school_id,NEW.cashier_user_id,'OFFLINE_PAYMENT_PROTOCOL_APPLIED','OFFLINE_PAYMENT_OPERATION',NEW.operation_id,
      'SYNC','SUCCESS',NEW.device_id,NEW.idempotency_key,
      jsonb_build_object('receiptNo',NEW.receipt_no,'currency',NEW.currency,'amount',NEW.amount,
                         'paymentId',NEW.payment_id,'leaseId',NEW.lease_id,'journalSeq',NEW.journal_seq)
    );
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_payment_applied_audit ON offline_payment_inbox;
CREATE TRIGGER trg_offline_payment_applied_audit AFTER UPDATE OF status ON offline_payment_inbox
FOR EACH ROW EXECUTE FUNCTION audit_offline_payment_applied();

REVOKE ALL ON FUNCTION next_offline_receipt_no(uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION assert_finance_writer_allowed(uuid,uuid,uuid,uuid,uuid) FROM PUBLIC;
