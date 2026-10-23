-- 0085 — School RBAC policy layer (owner decisions 2026-10-23, docs/architecture/SCHOOL_RBAC_AUDIT_2026-10-23.md).
-- STRICTLY ADDITIVE: no row deleted, no existing grant changed. Reversible with rollback/0085_school_rbac_policies.down.sql.
--   * capability lifecycle (ACTIVE / PLANNED / DEPRECATED / ALIAS), alias_of, replaced_by, school_adjustable;
--   * canonical *.export capabilities (format variants become ALIAS: same authorization);
--   * standard role + school GRANT − school REVOKE (rbac_school_role_policies): the standard role keeps its identity;
--   * protected capabilities of a standard role (rbac_role_constraints LOCKED: the school administrator's base);
--   * separation of duties as constraints ALLOW / WARN / REQUIRE_APPROVAL / BLOCK, school-overridable when allowed;
--   * change requests approved by a second access manager, never by the requester.
-- The data section is generated from contracts/CAPABILITY_REGISTRY.json (tools/ci/rbac_registry.py sql), the
-- canonical source; the CI checks the provisioned database against the registry.

ALTER TABLE capability_catalog ADD COLUMN IF NOT EXISTS lifecycle varchar(16) NOT NULL DEFAULT 'ACTIVE';
ALTER TABLE capability_catalog ADD COLUMN IF NOT EXISTS alias_of varchar(128);
ALTER TABLE capability_catalog ADD COLUMN IF NOT EXISTS replaced_by varchar(128);
ALTER TABLE capability_catalog ADD COLUMN IF NOT EXISTS school_adjustable boolean NOT NULL DEFAULT false;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='capability_catalog_lifecycle_chk') THEN
    ALTER TABLE capability_catalog ADD CONSTRAINT capability_catalog_lifecycle_chk CHECK (lifecycle IN ('ACTIVE','PLANNED','DEPRECATED','ALIAS'));
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='capability_catalog_alias_fk') THEN
    ALTER TABLE capability_catalog ADD CONSTRAINT capability_catalog_alias_fk FOREIGN KEY (alias_of) REFERENCES capability_catalog(code);
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS rbac_role_constraints (
  role_id uuid NOT NULL REFERENCES rbac_roles(id),
  capability_code varchar(128) NOT NULL REFERENCES capability_catalog(code),
  kind varchar(16) NOT NULL CHECK (kind IN ('LOCKED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (role_id, capability_code, kind)
);

CREATE TABLE IF NOT EXISTS rbac_school_role_policies (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  role_id uuid NOT NULL REFERENCES rbac_roles(id),
  capability_code varchar(128) NOT NULL REFERENCES capability_catalog(code),
  effect varchar(8) NOT NULL CHECK (effect IN ('GRANT','REVOKE')),
  reason text NOT NULL CHECK (length(trim(reason)) >= 5),
  active boolean NOT NULL DEFAULT true,
  request_id uuid,
  created_by_user_id uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  revoked_by_user_id uuid REFERENCES users(id),
  revoke_reason text,
  CHECK (active OR revoked_at IS NOT NULL)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_rbac_school_role_policy_active ON rbac_school_role_policies(school_id, role_id, capability_code) WHERE active;
CREATE INDEX IF NOT EXISTS idx_rbac_school_role_policy_lookup ON rbac_school_role_policies(school_id, role_id) WHERE active;

-- A policy only adjusts an active STANDARD school role with an ACTIVE adjustable capability; a REVOKE targets an
-- unprotected capability of the baseline, a GRANT a capability the baseline does not carry. Enforced in the database
-- so no caller can bypass it with direct SQL. A policy is immutable: it is withdrawn, never edited or reactivated.
CREATE OR REPLACE FUNCTION validate_rbac_school_role_policy() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE r record; k record; in_base boolean;
BEGIN
  IF TG_OP='UPDATE' THEN
    IF NEW.active AND NOT OLD.active THEN RAISE EXCEPTION 'A withdrawn school policy is never reactivated'; END IF;
    IF (NEW.school_id, NEW.role_id, NEW.capability_code, NEW.effect, NEW.reason) IS DISTINCT FROM
       (OLD.school_id, OLD.role_id, OLD.capability_code, OLD.effect, OLD.reason) THEN
      RAISE EXCEPTION 'A school policy is immutable: withdraw it and create a new one';
    END IF;
    RETURN NEW;
  END IF;
  SELECT id, kind, school_id, status INTO r FROM rbac_roles WHERE id=NEW.role_id;
  IF NOT FOUND OR r.kind<>'SCHOOL_STANDARD' OR r.school_id IS NOT NULL OR r.status<>'ACTIVE' THEN
    RAISE EXCEPTION 'A school policy only adjusts an active standard school role';
  END IF;
  SELECT lifecycle, school_adjustable INTO k FROM capability_catalog WHERE code=NEW.capability_code;
  IF k.lifecycle<>'ACTIVE' OR NOT k.school_adjustable THEN
    RAISE EXCEPTION 'Capability % is not adjustable by a school', NEW.capability_code;
  END IF;
  in_base := EXISTS (SELECT 1 FROM rbac_role_capabilities WHERE role_id=NEW.role_id AND capability_code=NEW.capability_code);
  IF NEW.effect='GRANT' AND in_base THEN RAISE EXCEPTION 'Capability % already belongs to the standard role', NEW.capability_code; END IF;
  IF NEW.effect='REVOKE' AND NOT in_base THEN RAISE EXCEPTION 'Capability % does not belong to the standard role', NEW.capability_code; END IF;
  IF NEW.effect='REVOKE' AND EXISTS (SELECT 1 FROM rbac_role_constraints WHERE role_id=NEW.role_id AND capability_code=NEW.capability_code AND kind='LOCKED') THEN
    RAISE EXCEPTION 'Capability % is protected for this role and cannot be withdrawn', NEW.capability_code;
  END IF;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS trg_validate_rbac_school_role_policy ON rbac_school_role_policies;
CREATE TRIGGER trg_validate_rbac_school_role_policy BEFORE INSERT OR UPDATE ON rbac_school_role_policies
  FOR EACH ROW EXECUTE FUNCTION validate_rbac_school_role_policy();

CREATE TABLE IF NOT EXISTS rbac_sod_rules (
  code varchar(64) PRIMARY KEY,
  kind varchar(24) NOT NULL CHECK (kind IN ('SELF','CAPABILITY_GRANT','PAIR')),
  effect varchar(20) NOT NULL CHECK (effect IN ('ALLOW','WARN','REQUIRE_APPROVAL','BLOCK')),
  school_overridable boolean NOT NULL DEFAULT true,
  label text NOT NULL,
  description text NOT NULL DEFAULT '',
  capabilities jsonb NOT NULL DEFAULT '[]'::jsonb,
  match_prefix varchar(64),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rbac_school_sod_overrides (
  school_id uuid NOT NULL REFERENCES schools(id),
  rule_code varchar(64) NOT NULL REFERENCES rbac_sod_rules(code),
  effect varchar(20) NOT NULL CHECK (effect IN ('ALLOW','WARN','REQUIRE_APPROVAL','BLOCK')),
  reason text NOT NULL CHECK (length(trim(reason)) >= 5),
  updated_by_user_id uuid REFERENCES users(id),
  updated_at timestamptz NOT NULL DEFAULT now(),
  version integer NOT NULL DEFAULT 1,
  PRIMARY KEY (school_id, rule_code)
);

CREATE TABLE IF NOT EXISTS rbac_change_requests (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  school_id uuid NOT NULL REFERENCES schools(id),
  kind varchar(24) NOT NULL CHECK (kind IN ('ROLE_POLICY','ROLE_ASSIGNMENT')),
  payload jsonb NOT NULL,
  rules jsonb NOT NULL DEFAULT '[]'::jsonb,
  status varchar(16) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','APPROVED','REJECTED','CANCELLED')),
  reason text NOT NULL CHECK (length(trim(reason)) >= 5),
  requested_by_user_id uuid NOT NULL REFERENCES users(id),
  requested_by_membership_id uuid NOT NULL,
  decided_by_user_id uuid REFERENCES users(id),
  decided_at timestamptz,
  decision_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status='PENDING' OR decided_at IS NOT NULL),
  CHECK (decided_by_user_id IS NULL OR status='CANCELLED' OR decided_by_user_id<>requested_by_user_id)   -- never self-approved
);
CREATE INDEX IF NOT EXISTS idx_rbac_change_requests_pending ON rbac_change_requests(school_id) WHERE status='PENDING';

ALTER TABLE rbac_role_constraints ENABLE ROW LEVEL SECURITY;
ALTER TABLE rbac_role_constraints FORCE ROW LEVEL SECURITY;
ALTER TABLE rbac_school_role_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE rbac_school_role_policies FORCE ROW LEVEL SECURITY;
ALTER TABLE rbac_sod_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE rbac_sod_rules FORCE ROW LEVEL SECURITY;
ALTER TABLE rbac_school_sod_overrides ENABLE ROW LEVEL SECURITY;
ALTER TABLE rbac_school_sod_overrides FORCE ROW LEVEL SECURITY;
ALTER TABLE rbac_change_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE rbac_change_requests FORCE ROW LEVEL SECURITY;

-- generated by tools/ci/rbac_registry.py sql from CAPABILITY_REGISTRY.json 2.0.0
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,prerequisites,outputs,sensitive,notes,registry_version,active) VALUES
('access.grants.exception','Utilisateurs & accès','Accès','Créer une exception individuelle temporaire','grant','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.permissions.assign','Utilisateurs & accès','Accès','Attribuer/retirer des permissions à un rôle','assign','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.roles.manage','Utilisateurs & accès','Accès','Créer/modifier un rôle','manage','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.roles.read','Utilisateurs & accès','Accès','Voir rôles et permissions','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.scopes.assign','Utilisateurs & accès','Accès','Attribuer un périmètre à une affectation','assign','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.users.activate','Utilisateurs & accès','Accès','Activer/désactiver un utilisateur','activate','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.users.create','Utilisateurs & accès','Accès','Créer un utilisateur','create','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.users.credentials.reset','Utilisateurs & accès','Accès','Réinitialiser les identifiants d’un utilisateur','reset','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.users.pin.self_change','Utilisateurs & accès','Accès','Changer son propre code secret','update','MEDIUM','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('access.users.read','Utilisateurs & accès','Accès','Voir les utilisateurs','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('access.users.update','Utilisateurs & accès','Accès','Modifier un utilisateur','update','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('audit.entity.history.read','Audit','Audit transversal','Voir l’historique d’une entité','read','HIGH','SERVER_ONLY',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('audit.school.export','Audit','Audit transversal','Exporter le journal d’audit','export','HIGH','SERVER_ONLY',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'["XLSX", "PDF"]'::jsonb,true,'','2.0.0',true),
('audit.school.filter','Audit','Audit transversal','Filtrer/rechercher les événements','read','HIGH','SERVER_ONLY',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('audit.school.read','Audit','Audit transversal','Consulter le journal d’audit école','read','HIGH','SERVER_ONLY',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('communications.compose','Notifications & communications','Communications','Rédiger un communiqué/message','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('communications.delivery.retry','Notifications & communications','Communications','Relancer une livraison échouée','retry','HIGH','QUEUE_UNTIL_ONLINE',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('communications.history.read','Notifications & communications','Communications','Voir historique et statut de livraison','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('communications.read','Notifications & communications','Communications','Voir les communications','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('communications.send.all_parents','Notifications & communications','Communications','Envoyer à tous les parents de l’école','send','CRITICAL','QUEUE_UNTIL_ONLINE',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('communications.send.class','Notifications & communications','Communications','Envoyer à une classe','send','HIGH','QUEUE_UNTIL_ONLINE',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('communications.send.individual','Notifications & communications','Communications','Envoyer à un parent/destinataire','send','HIGH','QUEUE_UNTIL_ONLINE',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('communications.send.section','Notifications & communications','Communications','Envoyer à une section','send','HIGH','QUEUE_UNTIL_ONLINE',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('communications.sms.bulk_send','Notifications & communications','SMS','Envoyer des SMS en masse','send','CRITICAL','QUEUE_UNTIL_ONLINE',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('communications.sms.send','Notifications & communications','SMS','Envoyer par SMS','send','HIGH','QUEUE_UNTIL_ONLINE',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('communications.templates.manage','Notifications & communications','Communications','Gérer les modèles de messages','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('contributions.read','Effectifs & dépôts','Dépôts matériels','Voir les dépôts matériels','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('contributions.record','Effectifs & dépôts','Dépôts matériels','Enregistrer un dépôt matériel élève','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('contributions.register.export_xlsx','Effectifs & dépôts','Dépôts matériels','Exporter le registre des contributions','export','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('contributions.register.read','Effectifs & dépôts','Dépôts matériels','Voir le registre des contributions','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('dashboard.school.drilldown','Tableau de bord','École','Ouvrir les cartes et vues détaillées','drilldown','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('dashboard.school.export','Tableau de bord','École','Exporter une vue de tableau de bord','export','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'["XLSX", "PDF"]'::jsonb,false,'','2.0.0',true),
('dashboard.school.print','Tableau de bord','École','Imprimer une vue de tableau de bord','print','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('dashboard.school.read','Tableau de bord','École','Voir le tableau de bord école','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('documents.history.read','Documents','Historique & sorties','Voir historique des documents générés','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('documents.open','Documents','Historique & sorties','Ouvrir un document généré','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('documents.print','Documents','Historique & sorties','Imprimer un document','print','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('documents.receipts.bundle.print','Documents','Historique & sorties','Imprimer un lot familial de reçus','print','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('documents.regenerate','Documents','Historique & sorties','Régénérer un document depuis les données','generate','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'','2.0.0',true),
('documents.student_import_template.export','Documents','Historique & sorties','Exporter le modèle d’import élèves','export','LOW','LOCAL_WRITE_SYNC',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('enrollments.arrears.read','Élèves & inscriptions','Inscriptions','Voir les arriérés historiques d’un élève','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('enrollments.collect_on_admission','Élèves & inscriptions','Inscriptions','Encaisser les obligations d’admission pendant l’inscription','collect','HIGH','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','["ACTIVE_ACADEMIC_YEAR", "AT_LEAST_ONE_ACTIVE_CLASS"]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('enrollments.create','Élèves & inscriptions','Inscriptions','Inscrire un ou plusieurs enfants','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','["ACTIVE_ACADEMIC_YEAR", "AT_LEAST_ONE_ACTIVE_CLASS"]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('enrollments.export','Élèves & inscriptions','Inscriptions','Exporter / imprimer la vue d’inscription','export','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : enrollments.export_pdf, enrollments.export_xlsx, enrollments.print','2.0.0',true),
('enrollments.export_pdf','Élèves & inscriptions','Inscriptions','Exporter la vue PDF','export','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('enrollments.export_xlsx','Élèves & inscriptions','Inscriptions','Exporter la vue Excel','export','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('enrollments.preview','Élèves & inscriptions','Inscriptions','Prévisualiser une inscription familiale','preview','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('enrollments.print','Élèves & inscriptions','Inscriptions','Imprimer la vue d’inscription','print','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('enrollments.read','Élèves & inscriptions','Inscriptions','Consulter les inscriptions','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('enrollments.reenroll','Élèves & inscriptions','Inscriptions','Réinscrire un élève connu','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','["ACTIVE_ACADEMIC_YEAR", "AT_LEAST_ONE_ACTIVE_CLASS"]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('enrollments.validate','Élèves & inscriptions','Inscriptions','Valider les inscriptions','validate','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','["ACTIVE_ACADEMIC_YEAR", "AT_LEAST_ONE_ACTIVE_CLASS"]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('families.children.read','Élèves & inscriptions','Familles & responsables','Voir les enfants du ménage','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('families.create','Élèves & inscriptions','Familles & responsables','Créer une famille/ménage','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('families.directory.export','Élèves & inscriptions','Familles','Exporter / imprimer le répertoire des familles','export','LOW','READ_CACHE',false,'["SCHOOL", "SECTION"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : families.directory.export_xlsx, families.directory.print_pdf','2.0.0',true),
('families.directory.export_xlsx','Élèves & inscriptions','Familles','Exporter le répertoire des familles','export','LOW','READ_CACHE',false,'["SCHOOL", "SECTION"]'::jsonb,'POINT4C_ENRICHED','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('families.directory.print_pdf','Élèves & inscriptions','Familles','Imprimer le répertoire des familles','print','LOW','READ_CACHE',false,'["SCHOOL", "SECTION"]'::jsonb,'POINT4C_ENRICHED','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('families.read','Élèves & inscriptions','Familles & responsables','Consulter les familles et ménages','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('families.resolution.audit','Élèves & inscriptions','Familles','Tracer la résolution de foyer','resolve','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL", "SECTION"]'::jsonb,'POINT4C_ENRICHED','[]'::jsonb,'[]'::jsonb,true,'Jamais de fusion silencieuse sur nom/téléphone','2.0.0',true),
('families.resolve','Élèves & inscriptions','Familles & responsables','Résoudre les candidats ménage/famille','resolve','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('families.responsibles.add','Élèves & inscriptions','Familles & responsables','Ajouter un responsable','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('families.responsibles.read','Élèves & inscriptions','Familles & responsables','Voir les responsables','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('families.responsibles.remove','Élèves & inscriptions','Familles & responsables','Retirer un responsable','delete','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('families.update','Élèves & inscriptions','Familles & responsables','Modifier une famille','update','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.advance_funds.allocate','Centre financier','Fonds anticipés','Imputer un fonds anticipé','allocate','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.advance_funds.read','Centre financier','Fonds anticipés','Voir les fonds anticipés','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.advance_funds.receipt.print','Centre financier','Fonds anticipés','Imprimer reçu de fonds anticipé','print','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('finance.advance_funds.receive','Centre financier','Fonds anticipés','Recevoir un fonds anticipé','collect','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.advance_funds.refund','Centre financier','Fonds anticipés','Rembourser un fonds anticipé non imputé','refund','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.analysis.advance.read','Centre financier','Analyses','Analyser les fonds anticipés','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.analysis.by_cashier.read','Centre financier','Analyses','Analyser par caissier','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.analysis.by_fee.read','Centre financier','Analyses','Analyser par type de frais','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.anticipation.collect','Centre financier','Plans anticipés','Encaisser selon un plan anticipé','collect','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.anticipation_membership.set','Centre financier','Plans anticipés','Enregistrer adhésion/refus parent','update','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.anticipation_plans.manage','Centre financier','Plans anticipés','Créer/modifier/activer un plan anticipé','manage','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.anticipation_plans.read','Centre financier','Plans anticipés','Voir les plans anticipés','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.cash.close','Centre financier','Caisse','Clôturer sa caisse','close','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.cash.day.close','Centre financier','Caisse','Clôturer la journée de caisse de l''école','close','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,false,'N3-A, décision du propriétaire du 2026-10-15','2.0.0',true),
('finance.cash.expense.create','Centre financier','Caisse','Enregistrer une dépense de caisse','create','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.cash.journal.export','Centre financier','Caisse','Exporter / imprimer le journal de caisse','export','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : finance.cash.journal.export_pdf, finance.cash.journal.print','2.0.0',true),
('finance.cash.journal.export_pdf','Centre financier','Caisse','Exporter le journal de caisse PDF','export','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('finance.cash.journal.print','Centre financier','Caisse','Imprimer le journal de caisse','print','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('finance.cash.open','Centre financier','Caisse','Ouvrir sa caisse','open','HIGH','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.cash.other.read','Centre financier','Caisse','Voir les autres caisses','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.cash.read','Centre financier','Caisse','Voir la caisse du jour','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.cash.reopen','Centre financier','Caisse','Réouvrir une caisse','reopen','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.checkout.allocate.preview','Centre financier','Encaissements & reçus','Prévisualiser les allocations','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.checkout.balance.read','Centre financier','Encaissements & reçus','Voir charges, payé et reste','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.checkout.collect','Centre financier','Encaissements & reçus','Encaisser un paiement','collect','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','["OPEN_CASH_SESSION"]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.checkout.family.collect','Centre financier','Encaissements & reçus','Encaisser un panier familial','collect','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','["OPEN_CASH_SESSION"]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.checkout.offline_cash','Centre financier','Encaissements & reçus','Encaisser CASH hors connexion sous autorisation','collect','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','["OPEN_CASH_SESSION"]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.checkout.recommend','Centre financier','Encaissements & reçus','Calculer le paiement recommandé','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.checkout.search','Centre financier','Encaissements & reçus','Rechercher élève/famille à encaisser','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.credits.read','Centre financier','Décisions financières','Voir crédits et trop-perçus','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.dashboard.read','Centre financier','Encaissements & reçus','Voir le tableau de bord financier','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.decisions.cancel','Centre financier','Décisions financières','Annuler une décision financière','cancel','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.decisions.create','Centre financier','Décisions financières','Créer réduction/exonération/faveur','create','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.decisions.read','Centre financier','Décisions financières','Voir les décisions financières','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.old_debt.collect','Centre financier','Anciennes dettes','Encaisser une ancienne dette','collect','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.old_debt.read','Centre financier','Anciennes dettes','Voir les anciennes dettes','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.payments.history.read','Centre financier','Encaissements & reçus','Voir l’historique des paiements','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.payments.reverse','Centre financier','Encaissements & reçus','Annuler/corriger un paiement par workflow officiel','reverse','CRITICAL','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.payments.reverse.supervisor','Centre financier','Encaissements & reçus','Annuler ou rembourser tout paiement (autorité supérieure)','reverse','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,false,'N3-A, décision du propriétaire du 2026-10-15','2.0.0',true),
('finance.products.manage','Centre financier','Articles scolaires','Configurer les articles scolaires','manage','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.products.read','Centre financier','Articles scolaires','Voir les articles scolaires','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.products.sale','Centre financier','Articles scolaires','Vendre et encaisser un article','collect','CRITICAL','PREAUTHORIZED_CRITICAL',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.products.sales_report.read','Centre financier','Articles scolaires','Voir le rapport des ventes','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.receipts.print','Centre financier','Encaissements & reçus','Imprimer un reçu','print','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('finance.receipts.read','Centre financier','Encaissements & reçus','Voir les reçus','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.receipts.reprint','Centre financier','Encaissements & reçus','Réimprimer un reçu/duplicata','reprint','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('finance.recovery.historical.read','Centre financier','Vues & recouvrement','Voir le recouvrement historique','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.recovery.monthly.read','Centre financier','Vues & recouvrement','Voir le suivi mensuel de recouvrement','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.reports.daily.generate','Centre financier','Rapports','Générer rapport financier journalier','generate','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.reports.history.read','Centre financier','Rapports','Voir l’historique des rapports','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.reports.periodic.export','Centre financier','Rapports','Exporter le rapport financier périodique','export','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : finance.reports.periodic.export_pdf, finance.reports.periodic.export_xlsx','2.0.0',true),
('finance.reports.periodic.export_pdf','Centre financier','Rapports','Exporter rapport périodique PDF','export','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('finance.reports.periodic.export_xlsx','Centre financier','Rapports','Exporter rapport périodique Excel','export','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('finance.reports.periodic.generate','Centre financier','Rapports','Générer rapport financier périodique','generate','HIGH','READ_CACHE',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.responsibility.read','Centre financier','Décisions financières','Voir les responsabilités financières prévues','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.responsibility.set','Centre financier','Décisions financières','Définir famille/paie/tiers responsable','update','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.views.summaries.export_xlsx','Centre financier','Vues & recouvrement','Exporter les synthèses VF-02/VF-03/VF-04','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('finance.views.vf01.export','Centre financier','Vues & recouvrement','Exporter / imprimer le registre VF-01','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : finance.views.vf01.export_pdf, finance.views.vf01.export_xlsx, finance.views.vf01.print','2.0.0',true),
('finance.views.vf01.export_pdf','Centre financier','Vues & recouvrement','Exporter VF-01 PDF officiel','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('finance.views.vf01.export_xlsx','Centre financier','Vues & recouvrement','Exporter VF-01 Excel','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('finance.views.vf01.print','Centre financier','Vues & recouvrement','Imprimer VF-01','print','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('finance.views.vf01.read','Centre financier','Vues & recouvrement','Voir registre financier détaillé VF-01','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.views.vf02.read','Centre financier','Vues & recouvrement','Voir synthèse classe VF-02','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.views.vf03.read','Centre financier','Vues & recouvrement','Voir synthèse section VF-03','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('finance.views.vf04.read','Centre financier','Vues & recouvrement','Voir synthèse école VF-04','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('headcounts.by_class.read','Effectifs & dépôts','Effectifs','Voir les effectifs par classe','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('headcounts.by_option.read','Effectifs & dépôts','Effectifs','Voir les effectifs par filière/option','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('headcounts.by_section.read','Effectifs & dépôts','Effectifs','Voir les effectifs par section','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('headcounts.export','Effectifs & dépôts','Effectifs','Exporter / imprimer les effectifs','export','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : headcounts.export_pdf, headcounts.export_xlsx, headcounts.print','2.0.0',true),
('headcounts.export_pdf','Effectifs & dépôts','Effectifs','Exporter les effectifs PDF','export','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('headcounts.export_xlsx','Effectifs & dépôts','Effectifs','Exporter les effectifs Excel','export','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('headcounts.movements.read','Effectifs & dépôts','Effectifs','Voir les mouvements d’effectifs','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('headcounts.print','Effectifs & dépôts','Effectifs','Imprimer les effectifs','print','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('headcounts.read','Effectifs & dépôts','Effectifs','Voir les effectifs','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.assets.create','Intendance','Biens durables','Enregistrer un bien durable','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.assets.history.read','Intendance','Biens durables','Voir historique du bien','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.assets.read','Intendance','Biens durables','Voir biens durables','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.assets.repair.record','Intendance','Biens durables','Enregistrer une réparation','create','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.assets.status.update','Intendance','Biens durables','Modifier état du bien','update','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.assets.update','Intendance','Biens durables','Modifier fiche/localisation du bien','update','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.counts.create','Intendance','Inventaires','Créer un inventaire','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.counts.export','Intendance','Inventaires','Exporter / imprimer un inventaire','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : inventory.counts.export_xlsx, inventory.counts.print','2.0.0',true),
('inventory.counts.export_xlsx','Intendance','Inventaires','Exporter inventaire Excel','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('inventory.counts.print','Intendance','Inventaires','Imprimer inventaire','print','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('inventory.counts.read','Intendance','Inventaires','Voir inventaires','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.counts.record','Intendance','Inventaires','Saisir comptage inventaire','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.counts.validate','Intendance','Inventaires','Valider un inventaire','validate','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.stock.adjust','Intendance','Stocks','Corriger un stock par mouvement justifié','adjust','CRITICAL','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.stock.export_xlsx','Intendance','Stocks','Exporter stocks/mouvements Excel','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('inventory.stock.issue','Intendance','Stocks','Enregistrer une sortie de stock avec motif/destination','create','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.stock.item.manage','Intendance','Stocks','Créer/modifier un article de stock','manage','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.stock.low_alerts.read','Intendance','Stocks','Voir alertes de stock faible','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.stock.movements.read','Intendance','Stocks','Voir mouvements de stock','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.stock.read','Intendance','Stocks','Voir stocks consommables','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.stock.receive','Intendance','Stocks','Enregistrer une entrée de stock','create','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('inventory.stock.sheet.print','Intendance','Stocks','Imprimer fiche de stock','print','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('migration.errors.export','Migration & import','Imports','Exporter les erreurs/rejets d’import','export','MEDIUM','LOCAL_WRITE_SYNC',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('migration.finance_history.analyze','Migration & import','Imports','Analyser une reprise financière historique','analyze','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.finance_history.execute','Migration & import','Imports','Exécuter une reprise financière historique','import','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.historical.finalize','Migration & import','Imports','Comptabiliser les lignes historiques prêtes','finalize','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.historical.reconcile','Migration & import','Imports','Rapprocher une ligne historique','reconcile','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.historical.stage','Migration & import','Imports','Stager un import historique','stage','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.staff.analyze','Migration & import','Imports','Analyser un fichier personnel','analyze','MEDIUM','SERVER_ONLY',false,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.staff.execute','Migration & import','Imports','Importer le personnel','import','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.students.analyze','Migration & import','Imports','Analyser un fichier élèves','analyze','MEDIUM','LOCAL_WRITE_SYNC',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.students.execute','Migration & import','Imports','Importer les élèves','import','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.students.simulate','Migration & import','Imports','Simuler un import','simulate','MEDIUM','LOCAL_WRITE_SYNC',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('migration.template.download','Migration & import','Imports','Télécharger modèle Excel d’import','download','LOW','LOCAL_WRITE_SYNC',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["XLSX"]'::jsonb,false,'','2.0.0',true),
('notifications.internal.configure','Notifications & communications','Notifications internes','Configurer les règles internes','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('notifications.internal.create','Notifications & communications','Notifications internes','Créer une notification interne','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('notifications.internal.dismiss','Notifications & communications','Notifications internes','Marquer/archiver une notification','update','LOW','LOCAL_WRITE_SYNC',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('notifications.internal.read','Notifications & communications','Notifications internes','Voir ses notifications internes','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('notifications.internal.read_all','Notifications & communications','Notifications internes','Voir toutes les notifications autorisées','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.access_link.manage','Personnel','Accès lié','Lier/délier un compte utilisateur','manage','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('personnel.access_link.read','Personnel','Accès lié','Voir le compte lié à un agent','read','MEDIUM','SERVER_ONLY',false,'["SCHOOL"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('personnel.activate','Personnel','Personnel','Activer/désactiver un agent','activate','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.assignments.add','Personnel','Fonctions & affectations','Ajouter une affectation','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.assignments.end','Personnel','Fonctions & affectations','Terminer une affectation','update','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.assignments.read','Personnel','Fonctions & affectations','Voir les affectations','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.create','Personnel','Personnel','Ajouter un agent','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.directory.export','Personnel','Annuaire & rapports','Exporter / imprimer le registre du personnel','export','LOW','READ_CACHE',false,'["SCHOOL", "SECTION"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : personnel.directory.export_xlsx, personnel.directory.print_pdf','2.0.0',true),
('personnel.directory.export_xlsx','Personnel','Annuaire & rapports','Exporter le registre du personnel','export','LOW','READ_CACHE',false,'["SCHOOL", "SECTION"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'["XLSX"]'::jsonb,false,'Export filtré par périmètre effectif','2.0.0',true),
('personnel.directory.print_pdf','Personnel','Annuaire & rapports','Imprimer le registre du personnel','print','LOW','READ_CACHE',false,'["SCHOOL", "SECTION"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'["PDF"]'::jsonb,false,'Export filtré par périmètre effectif','2.0.0',true),
('personnel.exit','Personnel','Cycle de vie','Enregistrer la sortie d''un agent','exit','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'[]'::jsonb,true,'Clôture affectations + désactivation appartenance liée dans une transaction','2.0.0',true),
('personnel.functions.manage','Personnel','Fonctions & affectations','Créer/modifier/activer une fonction','manage','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.functions.read','Personnel','Fonctions & affectations','Voir les fonctions/postes','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.history.read','Personnel','Cycle de vie','Consulter l''historique d''un agent','read','LOW','READ_CACHE',false,'["SCHOOL", "SECTION"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.payroll_deduction.cancel','Personnel','Enfants du personnel & paie','Annuler une retenue non-cash','cancel','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.payroll_deduction.confirm','Personnel','Enfants du personnel & paie','Confirmer une retenue à la source','confirm','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.profile.print_pdf','Personnel','Annuaire & rapports','Imprimer une fiche agent','print','LOW','READ_CACHE',false,'["SCHOOL", "SECTION"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'["PDF"]'::jsonb,false,'Fiche agent avec affectations visibles','2.0.0',true),
('personnel.reactivate','Personnel','Cycle de vie','Réactiver un ancien agent','reactivate','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'[]'::jsonb,true,'Ne rouvre jamais les anciennes affectations','2.0.0',true),
('personnel.read','Personnel','Personnel','Consulter le personnel','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.staff_children.finance_mode','Personnel','Enfants du personnel & paie','Définir le mode financier enfant du personnel','update','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.staff_children.link','Personnel','Enfants du personnel & paie','Lier explicitement un enfant à un agent','link','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'POINT4B_ENRICHED','[]'::jsonb,'[]'::jsonb,true,'Jamais déduit du responsable','2.0.0',true),
('personnel.staff_children.read','Personnel','Enfants du personnel & paie','Voir les enfants du personnel','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.summary.read','Personnel','Personnel','Voir la synthèse du personnel','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('personnel.update','Personnel','Personnel','Modifier un agent','update','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('platform.access.manage','Atelier Pro','Accès','Gouverner les appartenances et rôles standards des écoles','manage','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,true,'Décision produit: Manager système administre les accès techniques des écoles.','2.0.0',true),
('platform.audit.export','Atelier Pro','Écoles','Exporter l’audit de plateforme','export','HIGH','SERVER_ONLY',false,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('platform.audit.read','Atelier Pro','Écoles','Consulter l’audit de plateforme','read','HIGH','SERVER_ONLY',false,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('platform.collaborators.manage','Atelier Pro','Accès plateforme','Gérer les collaborateurs de plateforme','manage','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,true,'Réservé au Manager système pour déléguer sans transmettre tous ses pouvoirs.','2.0.0',true),
('platform.health.read','Atelier Pro','Écoles','Voir l’état technique des écoles','read','MEDIUM','SERVER_ONLY',false,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('platform.messaging.read','Atelier Pro','Messagerie','Voir l’état des fournisseurs, portefeuilles SMS et volumes d’envoi (sans le contenu des messages)','read','MEDIUM','SERVER_ONLY',false,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'Messagerie externe (2026-10) : supervision technique, jamais le corps des messages des écoles','2.0.0',true),
('platform.messaging.retry','Atelier Pro','Messagerie','Relancer un envoi e-mail ou push en échec définitif (motif obligatoire)','retry','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'Messagerie plateforme (2026-10) : relance manuelle auditée, idempotente, motif obligatoire ; jamais un SMS (portefeuille de l’école)','2.0.0',true),
('platform.notifications.system.send','Atelier Pro','Notifications système','Envoyer une notification système aux écoles/utilisateurs ciblés','send','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'OWNER_APPROVED','[]'::jsonb,'[]'::jsonb,true,'Capacité ajoutée et validée par Daniel pour le Manager système. La sélection des destinataires et le contenu sont audités.','2.0.0',true),
('platform.school_admin.bootstrap','Atelier Pro','Écoles','Créer/réinitialiser l’administrateur initial d’une école','bootstrap','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('platform.schools.activate','Atelier Pro','Écoles','Activer une école','activate','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('platform.schools.create','Atelier Pro','Écoles','Créer une école','create','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('platform.schools.read','Atelier Pro','Écoles','Voir les écoles de la plateforme','read','MEDIUM','SERVER_ONLY',false,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('platform.schools.suspend','Atelier Pro','Écoles','Suspendre une école','suspend','CRITICAL','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('platform.schools.update','Atelier Pro','Écoles','Modifier l’identité technique d’une école','update','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('platform.sms_wallet.adjust','Atelier Pro','Messagerie','Ajuster le portefeuille SMS d’une école (crédit ou débit motivé)','adjust','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'Messagerie plateforme (2026-10) : ajustement séparé de la recharge payée, motif obligatoire, second facteur récent','2.0.0',true),
('platform.sms_wallet.credit','Atelier Pro','Messagerie','Recharger le portefeuille SMS d’une école après paiement','credit','HIGH','SERVER_ONLY',true,'["PLATFORM"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'Messagerie externe (2026-10) : crédit manuel audité après paiement de l’école à EduSync, second facteur récent','2.0.0',true),
('settings.academic_year.activate','Paramètres','Année scolaire','Activer une année','activate','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.academic_year.archive','Paramètres','Année scolaire','Archiver une année','archive','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.academic_year.close','Paramètres','Année scolaire','Clôturer une année','close','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.academic_year.copy_previous','Paramètres','Année scolaire','Reprendre la configuration précédente','copy','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.academic_year.create','Paramètres','Année scolaire','Créer/préparer une année','create','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.academic_year.read','Paramètres','Année scolaire','Voir les années scolaires','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.academic_year.reopen','Paramètres','Année scolaire','Réouvrir pour correction','reopen','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.academic_year.update','Paramètres','Année scolaire','Modifier une année préparée','update','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.backups.create','Paramètres','Documents & sauvegardes','Créer une sauvegarde maintenant','create','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.backups.manage','Paramètres','Documents & sauvegardes','Modifier politique sauvegarde','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.backups.read','Paramètres','Documents & sauvegardes','Voir paramètres sauvegarde','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.backups.restore','Paramètres','Documents & sauvegardes','Restaurer une sauvegarde','restore','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.backups.test','Paramètres','Documents & sauvegardes','Tester une sauvegarde','test','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.benefits.manage','Paramètres','Avantages','Configurer famille nombreuse / enfant du personnel','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.benefits.read','Paramètres','Avantages','Voir politiques sociales','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.billing_months.manage','Paramètres','Tarifs & barèmes','Configurer les mois de facturation','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.classes.activate','Paramètres','Structure & classes','Activer/désactiver une classe','activate','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.classes.batch_create','Paramètres','Structure & classes','Créer plusieurs classes','create','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.classes.create','Paramètres','Structure & classes','Ouvrir une classe','create','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.classes.rename','Paramètres','Structure & classes','Renommer une classe','update','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.contributions.activate','Paramètres','Contributions en nature','Activer/désactiver une contribution','activate','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.contributions.manage','Paramètres','Contributions en nature','Créer/modifier une contribution','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.contributions.read','Paramètres','Contributions en nature','Voir contributions configurées','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.diagnostics.export','Paramètres','Options avancées','Exporter diagnostic','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["ZIP"]'::jsonb,false,'','2.0.0',true),
('settings.diagnostics.read','Paramètres','Options avancées','Voir diagnostic système','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.document_root.manage','Paramètres','Options avancées','Choisir dossier documentaire','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.documents.history.read','Paramètres','Documents & sauvegardes','Voir historique des documents','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.documents.manage','Paramètres','Documents & sauvegardes','Modifier préfixes/reçus/logo/signature','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.documents.read','Paramètres','Documents & sauvegardes','Voir paramètres documents','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.enrollment_policy.activate','Paramètres','Inscription & admission','Activer/désactiver une condition','activate','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.enrollment_policy.manage','Paramètres','Inscription & admission','Créer/modifier les conditions','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.enrollment_policy.read','Paramètres','Inscription & admission','Voir conditions d’inscription','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.enrollment_policy.review','Paramètres','Inscription & admission','Valider la revue des conditions','validate','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.fee_types.activate','Paramètres','Types de frais','Activer/désactiver un type de frais','activate','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.fee_types.manage','Paramètres','Types de frais','Créer/modifier un type de frais','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.fee_types.read','Paramètres','Types de frais','Voir types de frais','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.option_tariff_group.manage','Paramètres','Structure & classes','Gérer groupes tarifaires options','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.options.manage','Paramètres','Structure & classes','Activer/désactiver les options','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.payment_policy.manage','Paramètres','Règles d’encaissement','Modifier modes/acomptes/fonds/paiements futurs','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.payment_policy.read','Paramètres','Règles d’encaissement','Voir règles d’encaissement','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.products.activate','Paramètres','Articles scolaires vendus','Activer/désactiver un article','activate','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.products.manage','Paramètres','Articles scolaires vendus','Créer/modifier un article vendu','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.products.read','Paramètres','Articles scolaires vendus','Voir catalogue des articles vendus','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.regulatory_fees.configure','Paramètres','Types de frais','Configurer frais réglementaires','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.school_identity.read','Paramètres','École & identité','Voir identité école','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.school_identity.update','Paramètres','École & identité','Modifier identité école','update','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.school_logo.update','Paramètres','École & identité','Modifier logo école','update','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.sections.manage','Paramètres','Structure & classes','Activer/désactiver les sections','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.structure.read','Paramètres','Structure & classes','Voir structure et classes','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.tariff_groups.manage','Paramètres','Tarifs & barèmes','Gérer barèmes de groupe','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.tariffs.apply','Paramètres','Tarifs & barèmes','Appliquer les barèmes aux classes','apply','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.tariffs.copy_year','Paramètres','Tarifs & barèmes','Copier les barèmes vers une autre année','copy','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.tariffs.manage','Paramètres','Tarifs & barèmes','Créer/modifier un tarif','manage','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.tariffs.read','Paramètres','Tarifs & barèmes','Voir tarifs et barèmes','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('settings.work_year.select','Paramètres','Année scolaire','Changer année de consultation','select','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.account.export','Élèves & inscriptions','Élèves','Exporter / imprimer le relevé élève','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : students.account.export_pdf, students.account.print','2.0.0',true),
('students.account.export_pdf','Élèves & inscriptions','Élèves','Exporter le relevé élève PDF','export','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('students.account.print','Élèves & inscriptions','Élèves','Imprimer le relevé élève','print','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('students.account.read','Élèves & inscriptions','Élèves','Voir le compte/relevé élève','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.class.change','Élèves & inscriptions','Élèves','Changer la classe','update','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.create','Élèves & inscriptions','Élèves','Créer un nouvel élève','create','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.directory.export','Élèves & inscriptions','Annuaire','Exporter / imprimer l’annuaire des élèves','export','LOW','READ_CACHE',false,'["SCHOOL", "SECTION", "CLASS"]'::jsonb,'MERGED_2026_10_23','[]'::jsonb,'["PDF", "XLSX"]'::jsonb,false,'Fusion des variantes de format (décision propriétaire 2026-10-23) : students.directory.export_xlsx, students.directory.print_pdf','2.0.0',true),
('students.directory.export_xlsx','Élèves & inscriptions','Annuaire','Exporter l’annuaire des élèves','export','LOW','READ_CACHE',false,'["SCHOOL", "SECTION", "CLASS"]'::jsonb,'POINT4C_ENRICHED','[]'::jsonb,'["XLSX"]'::jsonb,false,'Respecte strictement le périmètre effectif','2.0.0',true),
('students.directory.print_pdf','Élèves & inscriptions','Annuaire','Imprimer l’annuaire des élèves','print','LOW','READ_CACHE',false,'["SCHOOL", "SECTION", "CLASS"]'::jsonb,'POINT4C_ENRICHED','[]'::jsonb,'["PDF"]'::jsonb,false,'Respecte strictement le périmètre effectif','2.0.0',true),
('students.identity.update','Élèves & inscriptions','Élèves','Modifier l’identité de l’élève','update','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.lifecycle.abandon','Élèves & inscriptions','Élèves','Déclarer un abandon avec date et motif','status','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.lifecycle.history.read','Élèves & inscriptions','Élèves','Voir l’historique du cycle de vie','read','MEDIUM','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.lifecycle.reintegrate','Élèves & inscriptions','Élèves','Réintégrer un élève','status','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.lifecycle.suspend','Élèves & inscriptions','Élèves','Suspendre un élève','suspend','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'N3-H (G-SCO-5) : mêmes titulaires que l''abandon (Desktop change_student_status)','2.0.0',true),
('students.lifecycle.transfer','Élèves & inscriptions','Élèves','Déclarer un transfert','status','HIGH','LOCAL_WRITE_SYNC',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('students.profile.complete','Élèves & inscriptions','Fiche élève','Compléter les informations non bloquantes','update','MEDIUM','LOCAL_WRITE_SYNC',true,'["SCHOOL", "SECTION", "CLASS"]'::jsonb,'POINT4C_ENRICHED','[]'::jsonb,'[]'::jsonb,true,'Naissance, sexe, nationalité, adresse complétables après inscription','2.0.0',true),
('students.profile.print_pdf','Élèves & inscriptions','Fiche élève','Imprimer la fiche élève','print','LOW','READ_CACHE',false,'["SCHOOL", "SECTION", "CLASS"]'::jsonb,'POINT4C_ENRICHED','[]'::jsonb,'["PDF"]'::jsonb,false,'','2.0.0',true),
('students.read','Élèves & inscriptions','Élèves','Consulter/rechercher les élèves','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true),
('sync.conflicts.read','Synchronisation & offline','Synchronisation','Voir les conflits de synchronisation','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('sync.conflicts.resolve','Synchronisation & offline','Synchronisation','Résoudre un conflit autorisé','resolve','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('sync.device.register','Synchronisation & offline','Synchronisation','Enregistrer un appareil','create','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('sync.device.revoke','Synchronisation & offline','Synchronisation','Révoquer un appareil','revoke','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('sync.finance.arm','Synchronisation & offline','Synchronisation','Armer un poste pour encaissement CASH offline','arm','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('sync.finance.quarantine.read','Synchronisation & offline','Synchronisation','Voir opérations/charges en quarantaine','read','HIGH','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('sync.finance.quarantine.resolve','Synchronisation & offline','Synchronisation','Résoudre une quarantaine financière','resolve','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('sync.finance.reconcile','Synchronisation & offline','Synchronisation','Réconcilier la Finance offline','reconcile','CRITICAL','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,true,'','2.0.0',true),
('sync.status.read','Synchronisation & offline','Synchronisation','Voir état de synchronisation','read','LOW','READ_CACHE',false,'["SCHOOL"]'::jsonb,'NEW_APPROVED','[]'::jsonb,'[]'::jsonb,false,'','2.0.0',true)
ON CONFLICT (code) DO NOTHING;
UPDATE capability_catalog k SET lifecycle=v.lifecycle, replaced_by=v.replaced_by, school_adjustable=v.adj, updated_at=now()
FROM (VALUES
('access.grants.exception','PLANNED',NULL,false),
('access.permissions.assign','ACTIVE',NULL,true),
('access.roles.manage','ACTIVE',NULL,true),
('access.roles.read','ACTIVE',NULL,true),
('access.scopes.assign','ACTIVE',NULL,true),
('access.users.activate','ACTIVE',NULL,true),
('access.users.create','ACTIVE',NULL,true),
('access.users.credentials.reset','ACTIVE',NULL,true),
('access.users.pin.self_change','PLANNED',NULL,false),
('access.users.read','ACTIVE',NULL,true),
('access.users.update','ACTIVE',NULL,true),
('audit.entity.history.read','ACTIVE',NULL,true),
('audit.school.export','PLANNED',NULL,false),
('audit.school.filter','ACTIVE',NULL,true),
('audit.school.read','ACTIVE',NULL,true),
('communications.compose','ACTIVE',NULL,true),
('communications.delivery.retry','ACTIVE',NULL,true),
('communications.history.read','ACTIVE',NULL,true),
('communications.read','ACTIVE',NULL,true),
('communications.send.all_parents','ACTIVE',NULL,true),
('communications.send.class','ACTIVE',NULL,true),
('communications.send.individual','ACTIVE',NULL,true),
('communications.send.section','ACTIVE',NULL,true),
('communications.sms.bulk_send','ACTIVE',NULL,true),
('communications.sms.send','ACTIVE',NULL,true),
('communications.templates.manage','ACTIVE',NULL,true),
('contributions.read','ACTIVE',NULL,true),
('contributions.record','ACTIVE',NULL,true),
('contributions.register.export_xlsx','ACTIVE',NULL,true),
('contributions.register.read','ACTIVE',NULL,true),
('dashboard.school.drilldown','DEPRECATED',NULL,false),
('dashboard.school.export','DEPRECATED',NULL,false),
('dashboard.school.print','DEPRECATED',NULL,false),
('dashboard.school.read','DEPRECATED',NULL,false),
('documents.history.read','ACTIVE',NULL,true),
('documents.open','ACTIVE',NULL,true),
('documents.print','PLANNED',NULL,false),
('documents.receipts.bundle.print','ACTIVE',NULL,true),
('documents.regenerate','PLANNED',NULL,false),
('documents.student_import_template.export','ACTIVE',NULL,true),
('enrollments.arrears.read','DEPRECATED','students.account.read',false),
('enrollments.collect_on_admission','PLANNED',NULL,false),
('enrollments.create','ACTIVE',NULL,true),
('enrollments.export','PLANNED',NULL,false),
('enrollments.export_pdf','ALIAS','enrollments.export',false),
('enrollments.export_xlsx','ALIAS','enrollments.export',false),
('enrollments.preview','DEPRECATED',NULL,false),
('enrollments.print','ALIAS','enrollments.export',false),
('enrollments.read','DEPRECATED',NULL,false),
('enrollments.reenroll','ACTIVE',NULL,true),
('enrollments.validate','PLANNED',NULL,false),
('families.children.read','DEPRECATED',NULL,false),
('families.create','DEPRECATED',NULL,false),
('families.directory.export','ACTIVE',NULL,true),
('families.directory.export_xlsx','ALIAS','families.directory.export',false),
('families.directory.print_pdf','ALIAS','families.directory.export',false),
('families.read','ACTIVE',NULL,true),
('families.resolution.audit','PLANNED',NULL,false),
('families.resolve','ACTIVE',NULL,true),
('families.responsibles.add','ACTIVE',NULL,true),
('families.responsibles.read','DEPRECATED',NULL,false),
('families.responsibles.remove','ACTIVE',NULL,true),
('families.update','ACTIVE',NULL,true),
('finance.advance_funds.allocate','ACTIVE',NULL,true),
('finance.advance_funds.read','ACTIVE',NULL,true),
('finance.advance_funds.receipt.print','ACTIVE',NULL,true),
('finance.advance_funds.receive','ACTIVE',NULL,true),
('finance.advance_funds.refund','ACTIVE',NULL,true),
('finance.analysis.advance.read','ACTIVE',NULL,true),
('finance.analysis.by_cashier.read','ACTIVE',NULL,true),
('finance.analysis.by_fee.read','ACTIVE',NULL,true),
('finance.anticipation.collect','ACTIVE',NULL,true),
('finance.anticipation_membership.set','ACTIVE',NULL,true),
('finance.anticipation_plans.manage','ACTIVE',NULL,true),
('finance.anticipation_plans.read','ACTIVE',NULL,true),
('finance.cash.close','ACTIVE',NULL,true),
('finance.cash.day.close','ACTIVE',NULL,true),
('finance.cash.expense.create','ACTIVE',NULL,true),
('finance.cash.journal.export','ACTIVE',NULL,true),
('finance.cash.journal.export_pdf','ALIAS','finance.cash.journal.export',false),
('finance.cash.journal.print','ALIAS','finance.cash.journal.export',false),
('finance.cash.open','ACTIVE',NULL,true),
('finance.cash.other.read','ACTIVE',NULL,true),
('finance.cash.read','ACTIVE',NULL,true),
('finance.cash.reopen','ACTIVE',NULL,true),
('finance.checkout.allocate.preview','DEPRECATED',NULL,false),
('finance.checkout.balance.read','ACTIVE',NULL,true),
('finance.checkout.collect','ACTIVE',NULL,true),
('finance.checkout.family.collect','ACTIVE',NULL,true),
('finance.checkout.offline_cash','PLANNED',NULL,false),
('finance.checkout.recommend','DEPRECATED',NULL,false),
('finance.checkout.search','ACTIVE',NULL,true),
('finance.credits.read','ACTIVE',NULL,true),
('finance.dashboard.read','DEPRECATED',NULL,false),
('finance.decisions.cancel','ACTIVE',NULL,true),
('finance.decisions.create','ACTIVE',NULL,true),
('finance.decisions.read','ACTIVE',NULL,true),
('finance.old_debt.collect','DEPRECATED',NULL,false),
('finance.old_debt.read','ACTIVE',NULL,true),
('finance.payments.history.read','PLANNED',NULL,false),
('finance.payments.reverse','ACTIVE',NULL,true),
('finance.payments.reverse.supervisor','ACTIVE',NULL,true),
('finance.products.manage','DEPRECATED','settings.products.manage',false),
('finance.products.read','ACTIVE',NULL,true),
('finance.products.sale','ACTIVE',NULL,true),
('finance.products.sales_report.read','ACTIVE',NULL,true),
('finance.receipts.print','ACTIVE',NULL,true),
('finance.receipts.read','ACTIVE',NULL,true),
('finance.receipts.reprint','ACTIVE',NULL,true),
('finance.recovery.historical.read','PLANNED',NULL,false),
('finance.recovery.monthly.read','ACTIVE',NULL,true),
('finance.reports.daily.generate','ACTIVE',NULL,true),
('finance.reports.history.read','ACTIVE',NULL,true),
('finance.reports.periodic.export','ACTIVE',NULL,true),
('finance.reports.periodic.export_pdf','ALIAS','finance.reports.periodic.export',false),
('finance.reports.periodic.export_xlsx','ALIAS','finance.reports.periodic.export',false),
('finance.reports.periodic.generate','ACTIVE',NULL,true),
('finance.responsibility.read','ACTIVE',NULL,true),
('finance.responsibility.set','ACTIVE',NULL,true),
('finance.views.summaries.export_xlsx','PLANNED',NULL,false),
('finance.views.vf01.export','ACTIVE',NULL,true),
('finance.views.vf01.export_pdf','ALIAS','finance.views.vf01.export',false),
('finance.views.vf01.export_xlsx','ALIAS','finance.views.vf01.export',false),
('finance.views.vf01.print','ALIAS','finance.views.vf01.export',false),
('finance.views.vf01.read','PLANNED',NULL,false),
('finance.views.vf02.read','PLANNED',NULL,false),
('finance.views.vf03.read','PLANNED',NULL,false),
('finance.views.vf04.read','PLANNED',NULL,false),
('headcounts.by_class.read','ACTIVE',NULL,true),
('headcounts.by_option.read','ACTIVE',NULL,true),
('headcounts.by_section.read','ACTIVE',NULL,true),
('headcounts.export','ACTIVE',NULL,true),
('headcounts.export_pdf','ALIAS','headcounts.export',false),
('headcounts.export_xlsx','ALIAS','headcounts.export',false),
('headcounts.movements.read','ACTIVE',NULL,true),
('headcounts.print','ALIAS','headcounts.export',false),
('headcounts.read','ACTIVE',NULL,true),
('inventory.assets.create','ACTIVE',NULL,true),
('inventory.assets.history.read','ACTIVE',NULL,true),
('inventory.assets.read','ACTIVE',NULL,true),
('inventory.assets.repair.record','PLANNED',NULL,false),
('inventory.assets.status.update','ACTIVE',NULL,true),
('inventory.assets.update','PLANNED',NULL,false),
('inventory.counts.create','ACTIVE',NULL,true),
('inventory.counts.export','PLANNED',NULL,false),
('inventory.counts.export_xlsx','ALIAS','inventory.counts.export',false),
('inventory.counts.print','ALIAS','inventory.counts.export',false),
('inventory.counts.read','ACTIVE',NULL,true),
('inventory.counts.record','ACTIVE',NULL,true),
('inventory.counts.validate','ACTIVE',NULL,true),
('inventory.stock.adjust','ACTIVE',NULL,true),
('inventory.stock.export_xlsx','PLANNED',NULL,false),
('inventory.stock.issue','ACTIVE',NULL,true),
('inventory.stock.item.manage','ACTIVE',NULL,true),
('inventory.stock.low_alerts.read','PLANNED',NULL,false),
('inventory.stock.movements.read','ACTIVE',NULL,true),
('inventory.stock.read','ACTIVE',NULL,true),
('inventory.stock.receive','ACTIVE',NULL,true),
('inventory.stock.sheet.print','PLANNED',NULL,false),
('migration.errors.export','PLANNED',NULL,false),
('migration.finance_history.analyze','ACTIVE',NULL,true),
('migration.finance_history.execute','ACTIVE',NULL,true),
('migration.historical.finalize','PLANNED',NULL,false),
('migration.historical.reconcile','PLANNED',NULL,false),
('migration.historical.stage','PLANNED',NULL,false),
('migration.staff.analyze','ACTIVE',NULL,true),
('migration.staff.execute','ACTIVE',NULL,true),
('migration.students.analyze','ACTIVE',NULL,true),
('migration.students.execute','ACTIVE',NULL,true),
('migration.students.simulate','PLANNED',NULL,false),
('migration.template.download','DEPRECATED','documents.student_import_template.export',false),
('notifications.internal.configure','ACTIVE',NULL,true),
('notifications.internal.create','ACTIVE',NULL,true),
('notifications.internal.dismiss','ACTIVE',NULL,true),
('notifications.internal.read','ACTIVE',NULL,true),
('notifications.internal.read_all','PLANNED',NULL,false),
('personnel.access_link.manage','ACTIVE',NULL,true),
('personnel.access_link.read','ACTIVE',NULL,true),
('personnel.activate','ACTIVE',NULL,true),
('personnel.assignments.add','ACTIVE',NULL,true),
('personnel.assignments.end','ACTIVE',NULL,true),
('personnel.assignments.read','ACTIVE',NULL,true),
('personnel.create','ACTIVE',NULL,true),
('personnel.directory.export','ACTIVE',NULL,true),
('personnel.directory.export_xlsx','ALIAS','personnel.directory.export',false),
('personnel.directory.print_pdf','ALIAS','personnel.directory.export',false),
('personnel.exit','ACTIVE',NULL,true),
('personnel.functions.manage','ACTIVE',NULL,true),
('personnel.functions.read','ACTIVE',NULL,true),
('personnel.history.read','ACTIVE',NULL,true),
('personnel.payroll_deduction.cancel','ACTIVE',NULL,true),
('personnel.payroll_deduction.confirm','ACTIVE',NULL,true),
('personnel.profile.print_pdf','ACTIVE',NULL,true),
('personnel.reactivate','ACTIVE',NULL,true),
('personnel.read','ACTIVE',NULL,true),
('personnel.staff_children.finance_mode','ACTIVE',NULL,true),
('personnel.staff_children.link','ACTIVE',NULL,true),
('personnel.staff_children.read','ACTIVE',NULL,true),
('personnel.summary.read','ACTIVE',NULL,true),
('personnel.update','ACTIVE',NULL,true),
('platform.access.manage','ACTIVE',NULL,false),
('platform.audit.export','ACTIVE',NULL,false),
('platform.audit.read','ACTIVE',NULL,false),
('platform.collaborators.manage','ACTIVE',NULL,false),
('platform.health.read','ACTIVE',NULL,false),
('platform.messaging.read','ACTIVE',NULL,false),
('platform.messaging.retry','ACTIVE',NULL,false),
('platform.notifications.system.send','ACTIVE',NULL,false),
('platform.school_admin.bootstrap','ACTIVE',NULL,false),
('platform.schools.activate','ACTIVE',NULL,false),
('platform.schools.create','ACTIVE',NULL,false),
('platform.schools.read','ACTIVE',NULL,false),
('platform.schools.suspend','ACTIVE',NULL,false),
('platform.schools.update','ACTIVE',NULL,false),
('platform.sms_wallet.adjust','ACTIVE',NULL,false),
('platform.sms_wallet.credit','ACTIVE',NULL,false),
('settings.academic_year.activate','ACTIVE',NULL,true),
('settings.academic_year.archive','ACTIVE',NULL,true),
('settings.academic_year.close','ACTIVE',NULL,true),
('settings.academic_year.copy_previous','ACTIVE',NULL,true),
('settings.academic_year.create','ACTIVE',NULL,true),
('settings.academic_year.read','ACTIVE',NULL,true),
('settings.academic_year.reopen','ACTIVE',NULL,true),
('settings.academic_year.update','ACTIVE',NULL,true),
('settings.backups.create','PLANNED',NULL,false),
('settings.backups.manage','ACTIVE',NULL,true),
('settings.backups.read','ACTIVE',NULL,true),
('settings.backups.restore','PLANNED',NULL,false),
('settings.backups.test','PLANNED',NULL,false),
('settings.benefits.manage','ACTIVE',NULL,true),
('settings.benefits.read','ACTIVE',NULL,true),
('settings.billing_months.manage','ACTIVE',NULL,true),
('settings.classes.activate','ACTIVE',NULL,true),
('settings.classes.batch_create','PLANNED',NULL,false),
('settings.classes.create','ACTIVE',NULL,true),
('settings.classes.rename','ACTIVE',NULL,true),
('settings.contributions.activate','ACTIVE',NULL,true),
('settings.contributions.manage','ACTIVE',NULL,true),
('settings.contributions.read','ACTIVE',NULL,true),
('settings.diagnostics.export','PLANNED',NULL,false),
('settings.diagnostics.read','PLANNED',NULL,false),
('settings.document_root.manage','PLANNED',NULL,false),
('settings.documents.history.read','DEPRECATED','documents.history.read',false),
('settings.documents.manage','ACTIVE',NULL,true),
('settings.documents.read','ACTIVE',NULL,true),
('settings.enrollment_policy.activate','ACTIVE',NULL,true),
('settings.enrollment_policy.manage','ACTIVE',NULL,true),
('settings.enrollment_policy.read','ACTIVE',NULL,true),
('settings.enrollment_policy.review','ACTIVE',NULL,true),
('settings.fee_types.activate','ACTIVE',NULL,true),
('settings.fee_types.manage','ACTIVE',NULL,true),
('settings.fee_types.read','ACTIVE',NULL,true),
('settings.option_tariff_group.manage','ACTIVE',NULL,true),
('settings.options.manage','ACTIVE',NULL,true),
('settings.payment_policy.manage','ACTIVE',NULL,true),
('settings.payment_policy.read','ACTIVE',NULL,true),
('settings.products.activate','ACTIVE',NULL,true),
('settings.products.manage','ACTIVE',NULL,true),
('settings.products.read','ACTIVE',NULL,true),
('settings.regulatory_fees.configure','PLANNED',NULL,false),
('settings.school_identity.read','ACTIVE',NULL,true),
('settings.school_identity.update','ACTIVE',NULL,true),
('settings.school_logo.update','DEPRECATED','settings.documents.manage',false),
('settings.sections.manage','ACTIVE',NULL,true),
('settings.structure.read','ACTIVE',NULL,true),
('settings.tariff_groups.manage','ACTIVE',NULL,true),
('settings.tariffs.apply','ACTIVE',NULL,true),
('settings.tariffs.copy_year','PLANNED',NULL,false),
('settings.tariffs.manage','ACTIVE',NULL,true),
('settings.tariffs.read','ACTIVE',NULL,true),
('settings.work_year.select','DEPRECATED',NULL,false),
('students.account.export','ACTIVE',NULL,true),
('students.account.export_pdf','ALIAS','students.account.export',false),
('students.account.print','ALIAS','students.account.export',false),
('students.account.read','ACTIVE',NULL,true),
('students.class.change','ACTIVE',NULL,true),
('students.create','DEPRECATED',NULL,false),
('students.directory.export','ACTIVE',NULL,true),
('students.directory.export_xlsx','ALIAS','students.directory.export',false),
('students.directory.print_pdf','ALIAS','students.directory.export',false),
('students.identity.update','ACTIVE',NULL,true),
('students.lifecycle.abandon','ACTIVE',NULL,true),
('students.lifecycle.history.read','PLANNED',NULL,false),
('students.lifecycle.reintegrate','ACTIVE',NULL,true),
('students.lifecycle.suspend','ACTIVE',NULL,true),
('students.lifecycle.transfer','ACTIVE',NULL,true),
('students.profile.complete','ACTIVE',NULL,true),
('students.profile.print_pdf','ACTIVE',NULL,true),
('students.read','ACTIVE',NULL,true),
('sync.conflicts.read','ACTIVE',NULL,true),
('sync.conflicts.resolve','ACTIVE',NULL,true),
('sync.device.register','ACTIVE',NULL,true),
('sync.device.revoke','ACTIVE',NULL,true),
('sync.finance.arm','PLANNED',NULL,false),
('sync.finance.quarantine.read','PLANNED',NULL,false),
('sync.finance.quarantine.resolve','PLANNED',NULL,false),
('sync.finance.reconcile','PLANNED',NULL,false),
('sync.status.read','ACTIVE',NULL,true)
) AS v(code,lifecycle,replaced_by,adj) WHERE k.code=v.code;
UPDATE capability_catalog k SET alias_of=v.alias_of FROM (VALUES
('enrollments.export_pdf','enrollments.export'),
('enrollments.export_xlsx','enrollments.export'),
('enrollments.print','enrollments.export'),
('families.directory.export_xlsx','families.directory.export'),
('families.directory.print_pdf','families.directory.export'),
('finance.cash.journal.export_pdf','finance.cash.journal.export'),
('finance.cash.journal.print','finance.cash.journal.export'),
('finance.reports.periodic.export_pdf','finance.reports.periodic.export'),
('finance.reports.periodic.export_xlsx','finance.reports.periodic.export'),
('finance.views.vf01.export_pdf','finance.views.vf01.export'),
('finance.views.vf01.export_xlsx','finance.views.vf01.export'),
('finance.views.vf01.print','finance.views.vf01.export'),
('headcounts.export_pdf','headcounts.export'),
('headcounts.export_xlsx','headcounts.export'),
('headcounts.print','headcounts.export'),
('inventory.counts.export_xlsx','inventory.counts.export'),
('inventory.counts.print','inventory.counts.export'),
('personnel.directory.export_xlsx','personnel.directory.export'),
('personnel.directory.print_pdf','personnel.directory.export'),
('students.account.export_pdf','students.account.export'),
('students.account.print','students.account.export'),
('students.directory.export_xlsx','students.directory.export'),
('students.directory.print_pdf','students.directory.export')
) AS v(code,alias_of) WHERE k.code=v.code;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['access.grants.exception','access.permissions.assign','access.roles.manage','access.roles.read','access.scopes.assign','access.users.activate','access.users.create','access.users.credentials.reset','access.users.pin.self_change','access.users.read','access.users.update','audit.entity.history.read','audit.school.export','audit.school.filter','audit.school.read','documents.history.read','documents.open','documents.regenerate','finance.anticipation_plans.manage','finance.anticipation_plans.read','notifications.internal.configure','notifications.internal.create','notifications.internal.dismiss','notifications.internal.read','notifications.internal.read_all','personnel.access_link.manage','personnel.access_link.read','settings.academic_year.activate','settings.academic_year.archive','settings.academic_year.close','settings.academic_year.copy_previous','settings.academic_year.create','settings.academic_year.read','settings.academic_year.reopen','settings.academic_year.update','settings.backups.create','settings.backups.manage','settings.backups.read','settings.backups.restore','settings.backups.test','settings.benefits.manage','settings.benefits.read','settings.billing_months.manage','settings.classes.activate','settings.classes.batch_create','settings.classes.create','settings.classes.rename','settings.contributions.activate','settings.contributions.manage','settings.contributions.read','settings.diagnostics.export','settings.diagnostics.read','settings.document_root.manage','settings.documents.history.read','settings.documents.manage','settings.documents.read','settings.enrollment_policy.activate','settings.enrollment_policy.manage','settings.enrollment_policy.read','settings.enrollment_policy.review','settings.fee_types.activate','settings.fee_types.manage','settings.fee_types.read','settings.option_tariff_group.manage','settings.options.manage','settings.payment_policy.manage','settings.payment_policy.read','settings.products.activate','settings.products.manage','settings.products.read','settings.regulatory_fees.configure','settings.school_identity.read','settings.school_identity.update','settings.school_logo.update','settings.sections.manage','settings.structure.read','settings.tariff_groups.manage','settings.tariffs.apply','settings.tariffs.copy_year','settings.tariffs.manage','settings.tariffs.read','settings.work_year.select','sync.conflicts.read','sync.conflicts.resolve','sync.device.register','sync.device.revoke','sync.finance.quarantine.read','sync.status.read']::varchar[]) c
  WHERE r.code='ADMIN_SYSTEME_ECOLE' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_constraints(role_id,capability_code,kind)
  SELECT r.id, c, 'LOCKED' FROM rbac_roles r, unnest(ARRAY['access.users.read','access.users.create','access.users.update','access.users.activate','access.users.credentials.reset','access.roles.read','access.roles.manage','access.permissions.assign','access.scopes.assign','audit.school.read','settings.school_identity.read','settings.academic_year.read','settings.structure.read','notifications.internal.read']::varchar[]) c
  WHERE r.code='ADMIN_SYSTEME_ECOLE' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['contributions.read','contributions.record','contributions.register.export_xlsx','contributions.register.read','dashboard.school.read','documents.history.read','documents.open','documents.print','documents.receipts.bundle.print','enrollments.arrears.read','enrollments.collect_on_admission','enrollments.create','enrollments.export','enrollments.export_pdf','enrollments.export_xlsx','enrollments.preview','enrollments.print','enrollments.read','enrollments.reenroll','enrollments.validate','families.children.read','families.create','families.directory.export','families.directory.export_xlsx','families.directory.print_pdf','families.read','families.resolution.audit','families.resolve','families.responsibles.add','families.responsibles.read','families.responsibles.remove','families.update','finance.advance_funds.allocate','finance.advance_funds.read','finance.advance_funds.receipt.print','finance.advance_funds.receive','finance.anticipation.collect','finance.anticipation_membership.set','finance.anticipation_plans.read','finance.cash.close','finance.cash.expense.create','finance.cash.journal.export','finance.cash.journal.export_pdf','finance.cash.journal.print','finance.cash.open','finance.cash.read','finance.checkout.allocate.preview','finance.checkout.balance.read','finance.checkout.collect','finance.checkout.family.collect','finance.checkout.offline_cash','finance.checkout.recommend','finance.checkout.search','finance.credits.read','finance.dashboard.read','finance.decisions.read','finance.old_debt.collect','finance.old_debt.read','finance.payments.history.read','finance.payments.reverse','finance.products.read','finance.products.sale','finance.products.sales_report.read','finance.receipts.print','finance.receipts.read','finance.receipts.reprint','finance.recovery.historical.read','finance.recovery.monthly.read','finance.reports.daily.generate','finance.reports.history.read','finance.responsibility.read','finance.views.vf01.export','finance.views.vf01.export_pdf','finance.views.vf01.export_xlsx','finance.views.vf01.print','finance.views.vf01.read','finance.views.vf02.read','migration.finance_history.analyze','migration.finance_history.execute','notifications.internal.dismiss','notifications.internal.read','settings.benefits.read','settings.contributions.read','settings.enrollment_policy.read','settings.fee_types.read','settings.payment_policy.read','settings.products.read','settings.tariffs.read','students.account.export','students.account.export_pdf','students.account.print','students.account.read','students.create','students.directory.export','students.directory.export_xlsx','students.directory.print_pdf','students.identity.update','students.lifecycle.abandon','students.lifecycle.history.read','students.lifecycle.suspend','students.profile.complete','students.profile.print_pdf','students.read','sync.finance.arm','sync.finance.quarantine.read','sync.finance.reconcile','sync.status.read']::varchar[]) c
  WHERE r.code='CAISSIER' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['audit.entity.history.read','communications.compose','communications.history.read','communications.read','communications.send.class','communications.send.individual','communications.send.section','communications.sms.bulk_send','communications.sms.send','dashboard.school.drilldown','dashboard.school.export','dashboard.school.print','dashboard.school.read','documents.history.read','documents.open','documents.print','enrollments.export','enrollments.export_pdf','enrollments.print','enrollments.read','families.children.read','families.read','families.responsibles.read','headcounts.by_class.read','headcounts.by_section.read','headcounts.export','headcounts.movements.read','headcounts.print','headcounts.read','notifications.internal.dismiss','notifications.internal.read','settings.academic_year.read','settings.school_identity.read','settings.structure.read','students.directory.export','students.directory.print_pdf','students.identity.update','students.lifecycle.history.read','students.profile.complete','students.profile.print_pdf','students.read']::varchar[]) c
  WHERE r.code='DIRECTEUR_DISCIPLINE' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['audit.entity.history.read','communications.compose','communications.history.read','communications.read','communications.send.class','communications.send.individual','communications.send.section','communications.sms.send','dashboard.school.drilldown','dashboard.school.export','dashboard.school.print','dashboard.school.read','documents.history.read','documents.open','documents.print','enrollments.export','enrollments.export_pdf','enrollments.export_xlsx','enrollments.print','enrollments.read','families.children.read','families.directory.export','families.directory.print_pdf','families.read','families.responsibles.read','headcounts.by_class.read','headcounts.by_option.read','headcounts.by_section.read','headcounts.export','headcounts.export_pdf','headcounts.export_xlsx','headcounts.movements.read','headcounts.print','headcounts.read','notifications.internal.dismiss','notifications.internal.read','settings.academic_year.read','settings.school_identity.read','settings.structure.read','students.directory.export','students.directory.export_xlsx','students.directory.print_pdf','students.lifecycle.history.read','students.profile.complete','students.profile.print_pdf','students.read']::varchar[]) c
  WHERE r.code='DIRECTEUR_ETUDES' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['audit.entity.history.read','communications.compose','communications.history.read','communications.read','communications.send.class','communications.send.individual','communications.send.section','communications.sms.bulk_send','communications.sms.send','dashboard.school.drilldown','dashboard.school.export','dashboard.school.print','dashboard.school.read','documents.history.read','documents.open','documents.print','enrollments.arrears.read','enrollments.export','enrollments.export_pdf','enrollments.export_xlsx','enrollments.print','enrollments.read','families.children.read','families.directory.export','families.directory.export_xlsx','families.directory.print_pdf','families.read','families.resolution.audit','families.responsibles.read','finance.advance_funds.read','finance.analysis.by_fee.read','finance.anticipation_plans.read','finance.checkout.balance.read','finance.credits.read','finance.dashboard.read','finance.decisions.read','finance.old_debt.read','finance.payments.history.read','finance.products.read','finance.products.sales_report.read','finance.receipts.read','finance.recovery.historical.read','finance.recovery.monthly.read','finance.reports.history.read','finance.reports.periodic.export','finance.reports.periodic.export_pdf','finance.reports.periodic.export_xlsx','finance.reports.periodic.generate','finance.responsibility.read','finance.views.summaries.export_xlsx','finance.views.vf01.export','finance.views.vf01.export_pdf','finance.views.vf01.export_xlsx','finance.views.vf01.print','finance.views.vf01.read','finance.views.vf02.read','finance.views.vf03.read','headcounts.by_class.read','headcounts.by_option.read','headcounts.by_section.read','headcounts.export','headcounts.export_pdf','headcounts.export_xlsx','headcounts.movements.read','headcounts.print','headcounts.read','migration.finance_history.analyze','migration.finance_history.execute','notifications.internal.dismiss','notifications.internal.read','personnel.assignments.read','personnel.directory.export','personnel.directory.export_xlsx','personnel.directory.print_pdf','personnel.functions.read','personnel.history.read','personnel.profile.print_pdf','personnel.read','personnel.summary.read','settings.academic_year.read','settings.fee_types.read','settings.school_identity.read','settings.structure.read','settings.tariffs.read','students.account.export','students.account.export_pdf','students.account.print','students.account.read','students.class.change','students.directory.export','students.directory.export_xlsx','students.directory.print_pdf','students.identity.update','students.lifecycle.abandon','students.lifecycle.history.read','students.lifecycle.reintegrate','students.lifecycle.suspend','students.lifecycle.transfer','students.profile.complete','students.profile.print_pdf','students.read']::varchar[]) c
  WHERE r.code='DIRECTION_SECTION' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['audit.entity.history.read','audit.school.export','audit.school.filter','audit.school.read','communications.history.read','communications.read','contributions.read','contributions.register.export_xlsx','contributions.register.read','dashboard.school.drilldown','dashboard.school.export','dashboard.school.print','dashboard.school.read','documents.history.read','documents.open','documents.print','enrollments.arrears.read','enrollments.export','enrollments.export_pdf','enrollments.export_xlsx','enrollments.print','enrollments.read','families.children.read','families.directory.export','families.directory.export_xlsx','families.directory.print_pdf','families.read','families.responsibles.read','finance.advance_funds.read','finance.advance_funds.receipt.print','finance.advance_funds.refund','finance.analysis.advance.read','finance.analysis.by_cashier.read','finance.analysis.by_fee.read','finance.anticipation_plans.read','finance.cash.day.close','finance.cash.journal.export','finance.cash.journal.export_pdf','finance.cash.journal.print','finance.cash.other.read','finance.cash.read','finance.cash.reopen','finance.checkout.allocate.preview','finance.checkout.balance.read','finance.checkout.recommend','finance.checkout.search','finance.credits.read','finance.dashboard.read','finance.decisions.cancel','finance.decisions.create','finance.decisions.read','finance.old_debt.read','finance.payments.history.read','finance.payments.reverse.supervisor','finance.products.read','finance.products.sales_report.read','finance.receipts.read','finance.recovery.historical.read','finance.recovery.monthly.read','finance.reports.daily.generate','finance.reports.history.read','finance.reports.periodic.export','finance.reports.periodic.export_pdf','finance.reports.periodic.export_xlsx','finance.reports.periodic.generate','finance.responsibility.read','finance.responsibility.set','finance.views.summaries.export_xlsx','finance.views.vf01.export','finance.views.vf01.export_pdf','finance.views.vf01.export_xlsx','finance.views.vf01.print','finance.views.vf01.read','finance.views.vf02.read','finance.views.vf03.read','finance.views.vf04.read','headcounts.by_class.read','headcounts.by_option.read','headcounts.by_section.read','headcounts.export','headcounts.export_pdf','headcounts.export_xlsx','headcounts.movements.read','headcounts.print','headcounts.read','inventory.assets.history.read','inventory.assets.read','inventory.counts.export','inventory.counts.export_xlsx','inventory.counts.print','inventory.counts.read','inventory.stock.export_xlsx','inventory.stock.low_alerts.read','inventory.stock.movements.read','inventory.stock.read','inventory.stock.sheet.print','migration.finance_history.analyze','migration.finance_history.execute','notifications.internal.read','notifications.internal.read_all','personnel.assignments.add','personnel.assignments.end','personnel.assignments.read','personnel.create','personnel.directory.export','personnel.directory.export_xlsx','personnel.directory.print_pdf','personnel.exit','personnel.functions.manage','personnel.functions.read','personnel.history.read','personnel.payroll_deduction.cancel','personnel.payroll_deduction.confirm','personnel.profile.print_pdf','personnel.read','personnel.staff_children.finance_mode','personnel.staff_children.read','personnel.summary.read','personnel.update','settings.academic_year.read','settings.benefits.read','settings.contributions.read','settings.documents.history.read','settings.documents.read','settings.enrollment_policy.read','settings.fee_types.read','settings.payment_policy.read','settings.products.read','settings.school_identity.read','settings.structure.read','settings.tariffs.read','students.account.export','students.account.export_pdf','students.account.print','students.account.read','students.directory.export','students.directory.export_xlsx','students.directory.print_pdf','students.lifecycle.history.read','students.profile.print_pdf','students.read']::varchar[]) c
  WHERE r.code='GESTIONNAIRE' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['audit.entity.history.read','documents.history.read','documents.open','documents.print','inventory.assets.create','inventory.assets.history.read','inventory.assets.read','inventory.assets.repair.record','inventory.assets.status.update','inventory.assets.update','inventory.counts.create','inventory.counts.export','inventory.counts.export_xlsx','inventory.counts.print','inventory.counts.read','inventory.counts.record','inventory.counts.validate','inventory.stock.adjust','inventory.stock.export_xlsx','inventory.stock.issue','inventory.stock.item.manage','inventory.stock.low_alerts.read','inventory.stock.movements.read','inventory.stock.read','inventory.stock.receive','inventory.stock.sheet.print','notifications.internal.dismiss','notifications.internal.read','personnel.read','settings.school_identity.read']::varchar[]) c
  WHERE r.code='INTENDANT' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['audit.entity.history.read','communications.compose','communications.history.read','communications.read','communications.send.class','communications.send.individual','communications.send.section','communications.sms.bulk_send','communications.sms.send','dashboard.school.drilldown','dashboard.school.export','dashboard.school.print','dashboard.school.read','documents.history.read','documents.open','documents.print','enrollments.arrears.read','enrollments.export','enrollments.export_pdf','enrollments.export_xlsx','enrollments.print','enrollments.read','families.children.read','families.directory.export','families.directory.export_xlsx','families.directory.print_pdf','families.read','families.resolution.audit','families.responsibles.read','finance.advance_funds.read','finance.analysis.by_fee.read','finance.anticipation_plans.read','finance.checkout.balance.read','finance.credits.read','finance.dashboard.read','finance.decisions.read','finance.old_debt.read','finance.payments.history.read','finance.products.read','finance.products.sales_report.read','finance.receipts.read','finance.recovery.historical.read','finance.recovery.monthly.read','finance.reports.history.read','finance.reports.periodic.export','finance.reports.periodic.export_pdf','finance.reports.periodic.export_xlsx','finance.reports.periodic.generate','finance.responsibility.read','finance.views.summaries.export_xlsx','finance.views.vf01.export','finance.views.vf01.export_pdf','finance.views.vf01.export_xlsx','finance.views.vf01.print','finance.views.vf01.read','finance.views.vf02.read','finance.views.vf03.read','headcounts.by_class.read','headcounts.by_option.read','headcounts.by_section.read','headcounts.export','headcounts.export_pdf','headcounts.export_xlsx','headcounts.movements.read','headcounts.print','headcounts.read','migration.finance_history.analyze','migration.finance_history.execute','notifications.internal.dismiss','notifications.internal.read','personnel.assignments.read','personnel.directory.export','personnel.directory.export_xlsx','personnel.directory.print_pdf','personnel.functions.read','personnel.history.read','personnel.profile.print_pdf','personnel.read','personnel.summary.read','settings.academic_year.read','settings.fee_types.read','settings.school_identity.read','settings.structure.read','settings.tariffs.read','students.account.export','students.account.export_pdf','students.account.print','students.account.read','students.class.change','students.directory.export','students.directory.export_xlsx','students.directory.print_pdf','students.identity.update','students.lifecycle.abandon','students.lifecycle.history.read','students.lifecycle.reintegrate','students.lifecycle.suspend','students.lifecycle.transfer','students.profile.complete','students.profile.print_pdf','students.read']::varchar[]) c
  WHERE r.code='PREFET_ETUDES' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['audit.entity.history.read','audit.school.export','audit.school.filter','audit.school.read','communications.history.read','communications.read','contributions.read','contributions.register.export_xlsx','contributions.register.read','dashboard.school.drilldown','dashboard.school.export','dashboard.school.print','dashboard.school.read','documents.history.read','documents.open','documents.print','enrollments.arrears.read','enrollments.export','enrollments.export_pdf','enrollments.export_xlsx','enrollments.print','enrollments.read','families.children.read','families.directory.export','families.directory.export_xlsx','families.directory.print_pdf','families.read','families.responsibles.read','finance.advance_funds.read','finance.advance_funds.receipt.print','finance.analysis.advance.read','finance.analysis.by_cashier.read','finance.analysis.by_fee.read','finance.anticipation_plans.read','finance.cash.journal.export','finance.cash.journal.export_pdf','finance.cash.journal.print','finance.cash.other.read','finance.cash.read','finance.checkout.allocate.preview','finance.checkout.balance.read','finance.checkout.recommend','finance.checkout.search','finance.credits.read','finance.dashboard.read','finance.decisions.read','finance.old_debt.read','finance.payments.history.read','finance.products.read','finance.products.sales_report.read','finance.receipts.read','finance.recovery.historical.read','finance.recovery.monthly.read','finance.reports.daily.generate','finance.reports.history.read','finance.reports.periodic.export','finance.reports.periodic.export_pdf','finance.reports.periodic.export_xlsx','finance.reports.periodic.generate','finance.responsibility.read','finance.views.summaries.export_xlsx','finance.views.vf01.export','finance.views.vf01.export_pdf','finance.views.vf01.export_xlsx','finance.views.vf01.print','finance.views.vf01.read','finance.views.vf02.read','finance.views.vf03.read','finance.views.vf04.read','headcounts.by_class.read','headcounts.by_option.read','headcounts.by_section.read','headcounts.export','headcounts.export_pdf','headcounts.export_xlsx','headcounts.movements.read','headcounts.print','headcounts.read','inventory.assets.history.read','inventory.assets.read','inventory.counts.export','inventory.counts.export_xlsx','inventory.counts.print','inventory.counts.read','inventory.stock.export_xlsx','inventory.stock.low_alerts.read','inventory.stock.movements.read','inventory.stock.read','inventory.stock.sheet.print','migration.finance_history.analyze','migration.finance_history.execute','notifications.internal.read','notifications.internal.read_all','personnel.assignments.read','personnel.directory.export','personnel.directory.export_xlsx','personnel.directory.print_pdf','personnel.functions.read','personnel.history.read','personnel.profile.print_pdf','personnel.read','personnel.staff_children.read','personnel.summary.read','settings.academic_year.read','settings.benefits.read','settings.contributions.read','settings.documents.history.read','settings.documents.read','settings.enrollment_policy.read','settings.fee_types.read','settings.payment_policy.read','settings.products.read','settings.school_identity.read','settings.structure.read','settings.tariffs.read','students.account.export','students.account.export_pdf','students.account.print','students.account.read','students.directory.export','students.directory.export_xlsx','students.directory.print_pdf','students.lifecycle.history.read','students.profile.print_pdf','students.read']::varchar[]) c
  WHERE r.code='PROMOTEUR' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['audit.entity.history.read','audit.school.export','audit.school.filter','audit.school.read','dashboard.school.drilldown','dashboard.school.export','dashboard.school.print','dashboard.school.read','documents.history.read','documents.open','documents.print','enrollments.arrears.read','enrollments.read','families.read','families.responsibles.read','finance.advance_funds.read','finance.advance_funds.receipt.print','finance.analysis.advance.read','finance.analysis.by_cashier.read','finance.analysis.by_fee.read','finance.anticipation_plans.read','finance.cash.journal.export','finance.cash.journal.export_pdf','finance.cash.journal.print','finance.cash.other.read','finance.cash.read','finance.checkout.allocate.preview','finance.checkout.balance.read','finance.checkout.recommend','finance.checkout.search','finance.credits.read','finance.dashboard.read','finance.decisions.read','finance.old_debt.read','finance.payments.history.read','finance.products.read','finance.products.sales_report.read','finance.receipts.print','finance.receipts.read','finance.recovery.historical.read','finance.recovery.monthly.read','finance.reports.daily.generate','finance.reports.history.read','finance.reports.periodic.export','finance.reports.periodic.export_pdf','finance.reports.periodic.export_xlsx','finance.reports.periodic.generate','finance.responsibility.read','finance.views.summaries.export_xlsx','finance.views.vf01.export','finance.views.vf01.export_pdf','finance.views.vf01.export_xlsx','finance.views.vf01.print','finance.views.vf01.read','finance.views.vf02.read','finance.views.vf03.read','finance.views.vf04.read','migration.finance_history.analyze','migration.finance_history.execute','notifications.internal.read','notifications.internal.read_all','settings.benefits.read','settings.contributions.read','settings.enrollment_policy.read','settings.fee_types.read','settings.payment_policy.read','settings.products.read','settings.tariffs.read','students.account.export','students.account.export_pdf','students.account.print','students.account.read','students.read']::varchar[]) c
  WHERE r.code='RESPONSABLE_FINANCE' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['communications.compose','communications.history.read','communications.read','communications.templates.manage','documents.history.read','documents.open','documents.print','documents.regenerate','enrollments.read','families.directory.export','families.directory.export_xlsx','families.directory.print_pdf','families.read','families.responsibles.read','headcounts.by_class.read','headcounts.by_section.read','headcounts.export','headcounts.export_pdf','headcounts.print','headcounts.read','notifications.internal.dismiss','notifications.internal.read','personnel.create','personnel.read','personnel.update','settings.academic_year.read','settings.documents.read','settings.school_identity.read','settings.structure.read','students.directory.export','students.directory.export_xlsx','students.directory.print_pdf','students.profile.complete','students.profile.print_pdf','students.read']::varchar[]) c
  WHERE r.code='SECRETARIAT' AND r.kind='SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['platform.audit.read','platform.health.read','platform.schools.read']::varchar[]) c
  WHERE r.code='COLLABORATEUR_PLATEFORME' AND r.kind='PLATFORM_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
  SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['platform.access.manage','platform.audit.export','platform.audit.read','platform.collaborators.manage','platform.health.read','platform.messaging.read','platform.messaging.retry','platform.notifications.system.send','platform.school_admin.bootstrap','platform.schools.activate','platform.schools.create','platform.schools.read','platform.schools.suspend','platform.schools.update','platform.sms_wallet.adjust','platform.sms_wallet.credit']::varchar[]) c
  WHERE r.code='MANAGER_SYSTEME' AND r.kind='PLATFORM_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
INSERT INTO rbac_sod_rules(code,kind,effect,school_overridable,label,description,capabilities,match_prefix) VALUES ('SELF_ELEVATION','SELF','BLOCK',false,'Personne n’approuve ni n’applique une élévation de ses propres droits','Modifier la politique d’un rôle que l’on détient, s’attribuer un rôle, approuver sa propre demande : toujours refusé.','[]'::jsonb,NULL) ON CONFLICT (code) DO NOTHING;
INSERT INTO rbac_sod_rules(code,kind,effect,school_overridable,label,description,capabilities,match_prefix) VALUES ('GOVERNANCE_GRANT','CAPABILITY_GRANT','REQUIRE_APPROVAL',true,'Ajouter un droit d’administration des accès à un rôle exige l’approbation d’un second gestionnaire','Toute capacité access.* ajoutée par politique d’école passe par une demande approuvée par un autre gestionnaire des accès.','[]'::jsonb,'access.') ON CONFLICT (code) DO NOTHING;
INSERT INTO rbac_sod_rules(code,kind,effect,school_overridable,label,description,capabilities,match_prefix) VALUES ('FIN_COLLECT_VS_SUPERVISOR_REVERSE','PAIR','WARN',true,'Encaisser et annuler tout paiement (autorité supérieure) chez la même personne','','["finance.checkout.collect", "finance.payments.reverse.supervisor"]'::jsonb,NULL) ON CONFLICT (code) DO NOTHING;
INSERT INTO rbac_sod_rules(code,kind,effect,school_overridable,label,description,capabilities,match_prefix) VALUES ('FIN_CASH_CLOSE_VS_REOPEN','PAIR','WARN',true,'Clôturer sa caisse et réouvrir une caisse chez la même personne','','["finance.cash.close", "finance.cash.reopen"]'::jsonb,NULL) ON CONFLICT (code) DO NOTHING;
INSERT INTO rbac_sod_rules(code,kind,effect,school_overridable,label,description,capabilities,match_prefix) VALUES ('FIN_DECISION_VS_COLLECT','PAIR','WARN',true,'Accorder réductions / exonérations et encaisser chez la même personne','','["finance.decisions.create", "finance.checkout.collect"]'::jsonb,NULL) ON CONFLICT (code) DO NOTHING;

-- Every role (standard or school-owned) holding a format variant also carries its canonical *.export capability, so
-- the rights editor (which hides ALIAS variants) shows what the role really allows. Insert only.
INSERT INTO rbac_role_capabilities(role_id, capability_code)
  SELECT DISTINCT rc.role_id, k.alias_of FROM rbac_role_capabilities rc JOIN capability_catalog k ON k.code=rc.capability_code AND k.alias_of IS NOT NULL
ON CONFLICT DO NOTHING;


DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='capability_catalog_alias_chk') THEN
    ALTER TABLE capability_catalog ADD CONSTRAINT capability_catalog_alias_chk CHECK ((lifecycle='ALIAS') = (alias_of IS NOT NULL));
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_platform') THEN
    DROP POLICY IF EXISTS rbac_role_constraints_platform ON rbac_role_constraints;
    CREATE POLICY rbac_role_constraints_platform ON rbac_role_constraints FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    DROP POLICY IF EXISTS rbac_school_role_policies_platform ON rbac_school_role_policies;
    CREATE POLICY rbac_school_role_policies_platform ON rbac_school_role_policies FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    DROP POLICY IF EXISTS rbac_sod_rules_platform ON rbac_sod_rules;
    CREATE POLICY rbac_sod_rules_platform ON rbac_sod_rules FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    DROP POLICY IF EXISTS rbac_school_sod_overrides_platform ON rbac_school_sod_overrides;
    CREATE POLICY rbac_school_sod_overrides_platform ON rbac_school_sod_overrides FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    DROP POLICY IF EXISTS rbac_change_requests_platform ON rbac_change_requests;
    CREATE POLICY rbac_change_requests_platform ON rbac_change_requests FOR ALL TO edusync_platform USING (true) WITH CHECK (true);
    GRANT SELECT ON rbac_role_constraints, rbac_sod_rules TO edusync_platform;
    GRANT SELECT, INSERT, UPDATE ON rbac_school_role_policies, rbac_school_sod_overrides, rbac_change_requests TO edusync_platform;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='edusync_tenant') THEN
    DROP POLICY IF EXISTS rbac_role_constraints_tenant_read ON rbac_role_constraints;
    CREATE POLICY rbac_role_constraints_tenant_read ON rbac_role_constraints FOR SELECT TO edusync_tenant USING (true);
    DROP POLICY IF EXISTS rbac_sod_rules_tenant_read ON rbac_sod_rules;
    CREATE POLICY rbac_sod_rules_tenant_read ON rbac_sod_rules FOR SELECT TO edusync_tenant USING (true);
    DROP POLICY IF EXISTS rbac_school_role_policies_tenant ON rbac_school_role_policies;
    CREATE POLICY rbac_school_role_policies_tenant ON rbac_school_role_policies FOR ALL TO edusync_tenant
      USING (school_id=nullif(current_setting('app.current_school_id',true),'')::uuid)
      WITH CHECK (school_id=nullif(current_setting('app.current_school_id',true),'')::uuid);
    DROP POLICY IF EXISTS rbac_school_sod_overrides_tenant ON rbac_school_sod_overrides;
    CREATE POLICY rbac_school_sod_overrides_tenant ON rbac_school_sod_overrides FOR ALL TO edusync_tenant
      USING (school_id=nullif(current_setting('app.current_school_id',true),'')::uuid)
      WITH CHECK (school_id=nullif(current_setting('app.current_school_id',true),'')::uuid);
    DROP POLICY IF EXISTS rbac_change_requests_tenant ON rbac_change_requests;
    CREATE POLICY rbac_change_requests_tenant ON rbac_change_requests FOR ALL TO edusync_tenant
      USING (school_id=nullif(current_setting('app.current_school_id',true),'')::uuid)
      WITH CHECK (school_id=nullif(current_setting('app.current_school_id',true),'')::uuid);
    GRANT SELECT ON rbac_role_constraints, rbac_sod_rules TO edusync_tenant;
    GRANT SELECT, INSERT, UPDATE ON rbac_school_role_policies, rbac_school_sod_overrides, rbac_change_requests TO edusync_tenant;
    REVOKE DELETE, TRUNCATE ON rbac_school_role_policies, rbac_school_sod_overrides, rbac_change_requests FROM edusync_tenant;
  END IF;
END $$;
