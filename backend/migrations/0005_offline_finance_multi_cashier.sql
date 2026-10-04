-- EduSync Point 2 — Finance offline multi-caissier, autorité partitionnée par charge.
-- Migration additive au protocole WEB-0D. Elle remplace l'exclusivité école entière par des
-- autorités disjointes au niveau de chaque charge. Deux leases peuvent donc coexister dans
-- la même école sans partager la même obligation financière.

ALTER TABLE offline_finance_leases
  ADD COLUMN IF NOT EXISTS protocol_version varchar(48) NOT NULL DEFAULT 'EXCLUSIVE_SINGLE_WRITER_CASH_V1';

DROP INDEX IF EXISTS uq_offline_finance_one_writer_per_school;
CREATE UNIQUE INDEX IF NOT EXISTS uq_offline_finance_active_device_session
  ON offline_finance_leases(school_id,device_id,cash_session_id)
  WHERE status IN ('PREPARING','ACTIVE','DRAINING');
CREATE INDEX IF NOT EXISTS idx_offline_finance_school_active
  ON offline_finance_leases(school_id,status,created_at);

ALTER TABLE offline_payment_inbox
  ADD COLUMN IF NOT EXISTS posting_outcome varchar(48),
  ADD COLUMN IF NOT EXISTS residual_credit_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK(residual_credit_amount >= 0);

CREATE TABLE IF NOT EXISTS offline_charge_reservations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  lease_id uuid NOT NULL REFERENCES offline_finance_leases(id) ON DELETE RESTRICT,
  charge_id uuid NOT NULL,
  currency varchar(3) NOT NULL CHECK(currency IN ('CDF','USD')),
  authorized_amount numeric(18,2) NOT NULL CHECK(authorized_amount > 0),
  consumed_amount numeric(18,2) NOT NULL DEFAULT 0 CHECK(consumed_amount >= 0 AND consumed_amount <= authorized_amount),
  status varchar(24) NOT NULL DEFAULT 'ACTIVE'
    CHECK(status IN ('ACTIVE','CLOSED','RELEASED','QUARANTINED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  quarantined_at timestamptz,
  released_at timestamptz,
  UNIQUE(lease_id,charge_id)
);

-- ACTIVE et QUARANTINED continuent tous les deux à bloquer l'autorité de la charge.
-- Une charge ne peut donc jamais être promise simultanément à deux appareils offline.
CREATE UNIQUE INDEX IF NOT EXISTS uq_offline_charge_one_live_authority
  ON offline_charge_reservations(school_id,charge_id)
  WHERE status IN ('ACTIVE','QUARANTINED');
CREATE INDEX IF NOT EXISTS idx_offline_charge_reservation_lease
  ON offline_charge_reservations(lease_id,status,charge_id);

CREATE TABLE IF NOT EXISTS offline_finance_incidents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  lease_id uuid NOT NULL REFERENCES offline_finance_leases(id) ON DELETE RESTRICT,
  actor_user_id uuid NOT NULL REFERENCES users(id),
  incident_type varchar(48) NOT NULL CHECK(incident_type IN ('FORCE_RELEASE','QUARANTINE_RESOLVED')),
  reason text NOT NULL CHECK(length(trim(reason)) >= 10),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_offline_finance_incident_lease ON offline_finance_incidents(lease_id,created_at);

-- Scope school_id défensif pour les nouvelles tables.
DROP TRIGGER IF EXISTS trg_offline_charge_reservation_scope ON offline_charge_reservations;
CREATE TRIGGER trg_offline_charge_reservation_scope BEFORE INSERT OR UPDATE ON offline_charge_reservations
FOR EACH ROW EXECUTE FUNCTION enforce_offline_finance_scope();
DROP TRIGGER IF EXISTS trg_offline_finance_incident_scope ON offline_finance_incidents;
CREATE TRIGGER trg_offline_finance_incident_scope BEFORE INSERT OR UPDATE ON offline_finance_incidents
FOR EACH ROW EXECUTE FUNCTION enforce_offline_finance_scope();

-- RLS strict tenant + accès plateforme, même doctrine que les autres artefacts offline.
DO $$
DECLARE t text;
BEGIN
  FOREACH t IN ARRAY ARRAY['offline_charge_reservations','offline_finance_incidents'] LOOP
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

-- Une opération Finance canonique doit appeler ce guard pour CHAQUE charge mutée.
-- Un writer online reste libre sur les charges non réservées; seule la charge sous autorité
-- offline est protégée. Cela maximise la disponibilité sans double vérité financière.
CREATE OR REPLACE FUNCTION assert_finance_charge_writer_allowed(
  p_school_id uuid,
  p_charge_id uuid,
  p_lease_id uuid DEFAULT NULL
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE r offline_charge_reservations%ROWTYPE;
BEGIN
  SELECT * INTO r FROM offline_charge_reservations
   WHERE school_id=p_school_id AND charge_id=p_charge_id AND status IN ('ACTIVE','QUARANTINED')
   FOR UPDATE;
  IF NOT FOUND THEN RETURN; END IF;
  IF r.status='QUARANTINED' THEN
    RAISE EXCEPTION 'finance_charge_quarantined_after_offline_incident';
  END IF;
  IF p_lease_id IS NULL OR r.lease_id<>p_lease_id THEN
    RAISE EXCEPTION 'finance_charge_reserved_by_offline_cashier';
  END IF;
END;
$$;

-- Le guard V1 global n'est plus un verrou d'école. En V2, il vérifie uniquement l'identité
-- du lease lorsque celui-ci est fourni. Tout adapter qui mute une charge DOIT en plus appeler
-- assert_finance_charge_writer_allowed; un ancien adapter sans charge-scope échoue explicitement
-- lorsqu'une autorité offline existe, au lieu de devenir silencieusement dangereux.
CREATE OR REPLACE FUNCTION assert_finance_writer_allowed(
  p_school_id uuid,
  p_user_id uuid,
  p_device_id uuid,
  p_cash_session_id uuid,
  p_lease_id uuid DEFAULT NULL
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE l offline_finance_leases%ROWTYPE;
BEGIN
  IF p_lease_id IS NULL THEN
    IF EXISTS (
      SELECT 1 FROM offline_charge_reservations r
      WHERE r.school_id=p_school_id AND r.status IN ('ACTIVE','QUARANTINED')
    ) THEN
      RAISE EXCEPTION 'finance_v2_requires_charge_scoped_guard';
    END IF;
    RETURN;
  END IF;
  SELECT * INTO l FROM offline_finance_leases WHERE id=p_lease_id AND school_id=p_school_id FOR UPDATE;
  IF NOT FOUND OR l.cashier_user_id<>p_user_id OR l.device_id<>p_device_id OR l.cash_session_id<>p_cash_session_id THEN
    RAISE EXCEPTION 'finance_offline_lease_identity_mismatch';
  END IF;
  IF l.status NOT IN ('ACTIVE','DRAINING') THEN
    RAISE EXCEPTION 'offline_lease_not_active';
  END IF;
END;
$$;

-- Protection transitions de réservation.
CREATE OR REPLACE FUNCTION protect_offline_charge_reservation() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP='DELETE' THEN RAISE EXCEPTION 'offline_charge_reservation_delete_forbidden'; END IF;
  IF OLD.school_id<>NEW.school_id OR OLD.lease_id<>NEW.lease_id OR OLD.charge_id<>NEW.charge_id
     OR OLD.currency<>NEW.currency OR OLD.authorized_amount<>NEW.authorized_amount THEN
    RAISE EXCEPTION 'offline_charge_reservation_identity_immutable';
  END IF;
  IF NEW.consumed_amount < OLD.consumed_amount OR NEW.consumed_amount > NEW.authorized_amount THEN
    RAISE EXCEPTION 'offline_charge_reservation_consumption_invalid';
  END IF;
  IF OLD.status='ACTIVE' AND NEW.status NOT IN ('ACTIVE','CLOSED','RELEASED','QUARANTINED') THEN
    RAISE EXCEPTION 'offline_charge_reservation_transition_invalid';
  ELSIF OLD.status IN ('CLOSED','RELEASED') AND NEW.status<>OLD.status THEN
    RAISE EXCEPTION 'offline_charge_reservation_terminal';
  ELSIF OLD.status='QUARANTINED' AND NEW.status NOT IN ('QUARANTINED','RELEASED') THEN
    RAISE EXCEPTION 'offline_charge_quarantine_requires_explicit_release';
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_charge_reservation_protect ON offline_charge_reservations;
CREATE TRIGGER trg_offline_charge_reservation_protect BEFORE UPDATE OR DELETE ON offline_charge_reservations
FOR EACH ROW EXECUTE FUNCTION protect_offline_charge_reservation();

-- Toute transition terminale du lease ferme ou met en quarantaine son autorité.
CREATE OR REPLACE FUNCTION cascade_offline_lease_authority_status() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status=NEW.status THEN RETURN NEW; END IF;
  IF NEW.status='CLOSED' THEN
    UPDATE offline_charge_reservations SET status='CLOSED',closed_at=now()
      WHERE lease_id=NEW.id AND status='ACTIVE';
  ELSIF NEW.status='FORCE_RELEASED' THEN
    IF OLD.status='PREPARING' THEN
      UPDATE offline_charge_reservations SET status='RELEASED',released_at=now()
        WHERE lease_id=NEW.id AND status='ACTIVE';
    ELSE
      UPDATE offline_charge_reservations SET status='QUARANTINED',quarantined_at=now()
        WHERE lease_id=NEW.id AND status='ACTIVE';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_lease_authority_status ON offline_finance_leases;
CREATE TRIGGER trg_offline_lease_authority_status AFTER UPDATE OF status ON offline_finance_leases
FOR EACH ROW EXECUTE FUNCTION cascade_offline_lease_authority_status();

-- Sortie de quarantaine volontaire, jamais automatique. Elle libère uniquement les charges
-- du lease concerné et exige une trace d'incident forte. Les rôles habilités seront décidés
-- au Point 3; cette migration ne leur attribue pas cette permission.
CREATE OR REPLACE FUNCTION resolve_offline_finance_quarantine(
  p_lease_id uuid,
  p_actor_user_id uuid,
  p_reason text
) RETURNS void LANGUAGE plpgsql AS $$
DECLARE v_school uuid;
BEGIN
  IF length(trim(COALESCE(p_reason,''))) < 10 THEN
    RAISE EXCEPTION 'incident_reason_required';
  END IF;
  SELECT school_id INTO v_school FROM offline_finance_leases WHERE id=p_lease_id AND status='FORCE_RELEASED' FOR UPDATE;
  IF v_school IS NULL THEN RAISE EXCEPTION 'force_released_lease_required'; END IF;
  IF EXISTS (SELECT 1 FROM offline_payment_inbox WHERE lease_id=p_lease_id AND status='RECEIVED') THEN
    RAISE EXCEPTION 'unapplied_offline_commands_block_quarantine_resolution';
  END IF;
  INSERT INTO offline_finance_incidents(school_id,lease_id,actor_user_id,incident_type,reason)
  VALUES(v_school,p_lease_id,p_actor_user_id,'QUARANTINE_RESOLVED',trim(p_reason));
  UPDATE offline_charge_reservations SET status='RELEASED',released_at=now()
    WHERE lease_id=p_lease_id AND status='QUARANTINED';
  INSERT INTO audit_events(school_id,actor_user_id,action,entity_type,entity_id,source,result,reason)
  VALUES(v_school,p_actor_user_id,'OFFLINE_FINANCE_QUARANTINE_RESOLVED','OFFLINE_FINANCE_LEASE',p_lease_id,'SYSTEM','SUCCESS',trim(p_reason));
END;
$$;

-- Audit force release: la procédure applicative écrit aussi l'incident; trigger DB couvre la
-- transition si elle vient d'un autre adapter autorisé.
CREATE OR REPLACE FUNCTION audit_offline_authority_quarantine() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF OLD.status IS DISTINCT FROM NEW.status AND NEW.status='QUARANTINED' THEN
    INSERT INTO audit_events(school_id,action,entity_type,entity_id,source,result,new_json)
    VALUES(NEW.school_id,'OFFLINE_CHARGE_AUTHORITY_QUARANTINED','OFFLINE_CHARGE_RESERVATION',NEW.id,
           'SYSTEM','SUCCESS',jsonb_build_object('leaseId',NEW.lease_id,'chargeId',NEW.charge_id,
                                                'authorizedAmount',NEW.authorized_amount,'consumedAmount',NEW.consumed_amount));
  END IF;
  RETURN NEW;
END;
$$;
DROP TRIGGER IF EXISTS trg_offline_authority_quarantine_audit ON offline_charge_reservations;
CREATE TRIGGER trg_offline_authority_quarantine_audit AFTER UPDATE OF status ON offline_charge_reservations
FOR EACH ROW EXECUTE FUNCTION audit_offline_authority_quarantine();

INSERT INTO permissions(code,label) VALUES
 ('finance.offline.incident.resolve','Résoudre une quarantaine Finance offline après rapprochement manuel')
ON CONFLICT(code) DO NOTHING;
-- Aucune attribution role_permissions ici: décision réservée au Point 3 avec Daniel.

REVOKE ALL ON FUNCTION assert_finance_charge_writer_allowed(uuid,uuid,uuid) FROM PUBLIC;
REVOKE ALL ON FUNCTION resolve_offline_finance_quarantine(uuid,uuid,text) FROM PUBLIC;
