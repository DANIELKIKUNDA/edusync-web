-- Messagerie plateforme industrialisée (lot 2026-10).
-- 1. Première tentative de chaque livraison (diagnostic : première / dernière / prochaine tentative).
ALTER TABLE communication_deliveries ADD COLUMN IF NOT EXISTS first_attempt_at timestamptz;
UPDATE communication_deliveries SET first_attempt_at = coalesce(last_attempt_at, sent_at, failed_at)
 WHERE first_attempt_at IS NULL AND attempts > 0;

-- 2. Recherche serveur de la file d'envoi (pagination par curseur, filtres canal / état / école).
CREATE INDEX IF NOT EXISTS idx_comm_delivery_created_desc ON communication_deliveries(created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_comm_delivery_channel_status ON communication_deliveries(channel, status, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_comm_delivery_school_created ON communication_deliveries(school_id, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_comm_delivery_message ON communication_deliveries(message_id);
CREATE INDEX IF NOT EXISTS idx_comm_delivery_failed_recent ON communication_deliveries(channel, failed_at DESC) WHERE status = 'FAILED_PERMANENT';
CREATE INDEX IF NOT EXISTS idx_comm_delivery_sent_recent ON communication_deliveries(channel, sent_at DESC) WHERE sent_at IS NOT NULL;

-- 3. Capacités séparées (mandat : aucune capacité implicite par simple accès à la page).
--    * relancer une livraison en échec définitif (e-mail / push ; un SMS se relance côté école : il engage son portefeuille) ;
--    * ajuster un portefeuille SMS (crédit / débit motivé), distinct de la recharge payée.
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,registry_version) VALUES
 ('platform.messaging.retry','Atelier Pro','Messagerie','Relancer un envoi e-mail ou push en échec définitif (motif obligatoire)','retry','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','0.84.0'),
 ('platform.sms_wallet.adjust','Atelier Pro','Messagerie','Ajuster le portefeuille SMS d’une école (crédit ou débit motivé)','adjust','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','0.84.0')
ON CONFLICT(code) DO NOTHING;
UPDATE capability_catalog SET label = 'Recharger le portefeuille SMS d’une école après paiement' WHERE code = 'platform.sms_wallet.credit';
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT r.id,c.code FROM rbac_roles r JOIN capability_catalog c ON c.code IN ('platform.messaging.retry','platform.sms_wallet.adjust')
WHERE r.code='MANAGER_SYSTEME' AND r.kind='PLATFORM_STANDARD'
ON CONFLICT DO NOTHING;

-- 4. Relance plateforme : mise à jour possible uniquement des livraisons e-mail / push (jamais un SMS).
DO $$ BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    GRANT UPDATE (status, attempts, next_attempt_at, last_error_code, last_error_detail, failed_at) ON communication_deliveries TO edusync_platform;
    DROP POLICY IF EXISTS platform_delivery_retry ON communication_deliveries;
    CREATE POLICY platform_delivery_retry ON communication_deliveries FOR UPDATE TO edusync_platform
      USING (channel IN ('EMAIL','PUSH')) WITH CHECK (channel IN ('EMAIL','PUSH'));
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_worker') THEN
    GRANT UPDATE (first_attempt_at) ON communication_deliveries TO edusync_worker;
  END IF;
END $$;
