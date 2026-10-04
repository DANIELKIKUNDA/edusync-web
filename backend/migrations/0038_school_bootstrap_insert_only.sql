-- An AFTER INSERT trigger runs once for a new school UUID. No row can pre-exist.
-- Avoid an ON CONFLICT target, which requires SELECT on tenant settings even
-- though the platform role intentionally only has INSERT access to defaults.
CREATE OR REPLACE FUNCTION provision_school_settings_defaults() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE suggested text;
BEGIN
  suggested := extract(year from CURRENT_DATE)::int || '-' || (extract(year from CURRENT_DATE)::int + 1);
  INSERT INTO settings_bootstrap_state(school_id,suggested_year_code) VALUES (NEW.id,suggested);
  INSERT INTO school_policy_documents(school_id,kind,payload) VALUES
    (NEW.id,'PAYMENT','{"allow_partial_payments":true,"currencies":["CDF","USD"],"implicit_currency_conversion":false}'::jsonb),
    (NEW.id,'DOCUMENTS','{"receipt_numbering":"SERVER_SEQUENCE","document_history":true}'::jsonb),
    (NEW.id,'BACKUP','{"enabled":true,"offsite_required":true}'::jsonb),
    (NEW.id,'COMMUNICATIONS','{"internal_notifications":true,"external_sms_enabled":false}'::jsonb);
  RETURN NEW;
END $$;
