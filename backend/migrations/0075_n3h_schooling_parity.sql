-- N3-H — schooling parity (Desktop golden master).
-- G-SCO-5: suspension (Desktop change_status_status SUSPENSION, same roles as abandon / transfer / reintegration:
-- ADMIN, SECRETARIAT, CAISSIER, DIRECTION). The Web capability did not exist; it is granted to the standard roles that
-- already hold the closest Desktop operation, the abandon (students.lifecycle.abandon). No other role is widened.
INSERT INTO capability_catalog(code,domain_name,group_name,label,action_code,risk,offline_policy,audit_required,scope_types,source_status,registry_version) VALUES
 ('students.lifecycle.suspend','Élèves & inscriptions','Élèves','Suspendre un élève','suspend','HIGH','SERVER_ONLY',true,'["SCHOOL"]'::jsonb,'EXISTING_DESKTOP','0.75.0')
ON CONFLICT(code) DO NOTHING;
INSERT INTO rbac_role_capabilities(role_id,capability_code)
SELECT DISTINCT rc.role_id,'students.lifecycle.suspend' FROM rbac_role_capabilities rc JOIN rbac_roles r ON r.id=rc.role_id AND r.kind='SCHOOL_STANDARD'
 WHERE rc.capability_code='students.lifecycle.abandon'
ON CONFLICT DO NOTHING;

-- G-EFF-1: Desktop contribution_item_types.required_quantity — the register shows required / delivered / remaining.
ALTER TABLE contribution_types ADD COLUMN IF NOT EXISTS required_quantity numeric(18,3) NOT NULL DEFAULT 0 CHECK (required_quantity >= 0);
