-- Point 4A — upgrade bridge: legacy SCHOOL_ADMIN -> industrial ADMIN_SYSTEME_ECOLE only.
-- No other legacy job title is guessed or silently remapped.
WITH candidates AS (
  SELECT m.id AS membership_id,m.user_id,m.school_id,nr.id AS role_id
    FROM school_memberships m
    JOIN membership_roles mr ON mr.membership_id=m.id
    JOIN roles lr ON lr.id=mr.role_id AND lr.code='SCHOOL_ADMIN'
    JOIN rbac_roles nr ON nr.code='ADMIN_SYSTEME_ECOLE' AND nr.kind='SCHOOL_STANDARD' AND nr.status='ACTIVE'
   WHERE m.active=true
), inserted AS (
  INSERT INTO rbac_assignments(user_id,role_id,school_id,membership_id,active,reason)
  SELECT c.user_id,c.role_id,c.school_id,c.membership_id,true,'MIGRATION_LEGACY_SCHOOL_ADMIN'
    FROM candidates c
   WHERE NOT EXISTS (
     SELECT 1 FROM rbac_assignments a
      WHERE a.membership_id=c.membership_id AND a.role_id=c.role_id AND a.active=true
   )
  RETURNING id
)
INSERT INTO rbac_assignment_scopes(assignment_id,scope_type,scope_value)
SELECT id,'SCHOOL',NULL FROM inserted
ON CONFLICT DO NOTHING;
