-- POINT 10B: robust optional communications, PostgreSQL source of truth + Redis-backed worker queue.
CREATE TABLE IF NOT EXISTS communication_settings (
 school_id uuid PRIMARY KEY REFERENCES schools(id) ON DELETE CASCADE,
 enabled boolean NOT NULL DEFAULT false,
 in_app_enabled boolean NOT NULL DEFAULT true,
 sms_enabled boolean NOT NULL DEFAULT false,
 email_enabled boolean NOT NULL DEFAULT false,
 whatsapp_enabled boolean NOT NULL DEFAULT false,
 provider_code varchar(64), sender_id varchar(32),
 prepaid_balance numeric(18,4), balance_currency varchar(8),
 low_balance_threshold numeric(18,4), updated_at timestamptz NOT NULL DEFAULT now(), version integer NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS communication_templates (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 code varchar(96) NOT NULL, label varchar(180) NOT NULL, event_type varchar(128), channel varchar(16) NOT NULL,
 body text NOT NULL, enabled boolean NOT NULL DEFAULT true, system_template boolean NOT NULL DEFAULT false,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), version integer NOT NULL DEFAULT 1,
 UNIQUE(school_id,code,channel)
);
CREATE TABLE IF NOT EXISTS communication_messages (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 kind varchar(24) NOT NULL, event_type varchar(128), template_id uuid REFERENCES communication_templates(id),
 audience_type varchar(24) NOT NULL, audience_ref uuid, subject varchar(180), body text NOT NULL,
 created_by uuid REFERENCES users(id), correlation_id uuid, idempotency_key varchar(180),
 created_at timestamptz NOT NULL DEFAULT now(), UNIQUE(school_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS communication_deliveries (
 id uuid PRIMARY KEY DEFAULT gen_random_uuid(), school_id uuid NOT NULL REFERENCES schools(id) ON DELETE CASCADE,
 message_id uuid NOT NULL REFERENCES communication_messages(id) ON DELETE CASCADE, channel varchar(16) NOT NULL,
 recipient_ref uuid, destination varchar(320), status varchar(24) NOT NULL DEFAULT 'PENDING',
 provider_code varchar(64), provider_message_id varchar(180), attempts integer NOT NULL DEFAULT 0,
 next_attempt_at timestamptz, last_error_code varchar(80), last_error_detail text,
 queued_at timestamptz, sent_at timestamptz, delivered_at timestamptz, failed_at timestamptz,
 estimated_segments integer, estimated_cost numeric(18,4), created_at timestamptz NOT NULL DEFAULT now(),
 UNIQUE(message_id,channel,destination)
);
CREATE INDEX IF NOT EXISTS idx_comm_delivery_work ON communication_deliveries(status,next_attempt_at,created_at);
ALTER TABLE communication_settings ENABLE ROW LEVEL SECURITY; ALTER TABLE communication_settings FORCE ROW LEVEL SECURITY;
ALTER TABLE communication_templates ENABLE ROW LEVEL SECURITY; ALTER TABLE communication_templates FORCE ROW LEVEL SECURITY;
ALTER TABLE communication_messages ENABLE ROW LEVEL SECURITY; ALTER TABLE communication_messages FORCE ROW LEVEL SECURITY;
ALTER TABLE communication_deliveries ENABLE ROW LEVEL SECURITY; ALTER TABLE communication_deliveries FORCE ROW LEVEL SECURITY;
DO $$ DECLARE t text; BEGIN FOREACH t IN ARRAY ARRAY['communication_settings','communication_templates','communication_messages','communication_deliveries'] LOOP
 EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I',t);
 EXECUTE format('CREATE POLICY tenant_isolation ON %I USING (school_id=current_setting(''app.school_id'',true)::uuid) WITH CHECK (school_id=current_setting(''app.school_id'',true)::uuid)',t);
 END LOOP; END $$;
GRANT SELECT,INSERT,UPDATE ON communication_settings,communication_templates,communication_messages,communication_deliveries TO edusync_tenant;
REVOKE DELETE ON communication_settings,communication_templates,communication_messages,communication_deliveries FROM edusync_tenant;
