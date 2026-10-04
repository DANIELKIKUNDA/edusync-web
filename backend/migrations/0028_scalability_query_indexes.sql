-- Point 10H6 — query-driven indexes for school and platform hot paths.
-- Keep indexes tenant-first; validate usage with pg_stat_statements + EXPLAIN (ANALYZE, BUFFERS).
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- Directory/search hot paths (ILIKE contains searches need trigram indexes; btree alone cannot serve %term%).
CREATE INDEX IF NOT EXISTS idx_students_school_matricule_trgm ON students USING gin (school_id, matricule gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_students_school_last_name_trgm ON students USING gin (school_id, last_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_families_display_name_trgm ON families USING gin (school_id, display_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_guardians_full_name_trgm ON guardians USING gin (school_id, full_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_staff_last_name_trgm ON staff_members USING gin (school_id, last_name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_staff_employee_no_trgm ON staff_members USING gin (school_id, employee_no gin_trgm_ops);

-- Enrollment/read-model joins and lifecycle history.
CREATE INDEX IF NOT EXISTS idx_enrollments_school_student_year_status ON enrollments(school_id,student_id,academic_year_id,status);
CREATE INDEX IF NOT EXISTS idx_enrollments_school_year_status_class ON enrollments(school_id,academic_year_id,status,class_id);
CREATE INDEX IF NOT EXISTS idx_family_guardians_active_family ON family_guardians(school_id,family_id,is_primary DESC,created_at) WHERE active;
CREATE INDEX IF NOT EXISTS idx_staff_assignments_school_open_order ON staff_assignments(school_id,staff_id,is_primary DESC,function_id) WHERE end_date IS NULL;

-- Audit/operational observability.
CREATE INDEX IF NOT EXISTS idx_audit_school_occurred ON audit_events(school_id,occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_entity_history ON audit_events(school_id,entity_type,entity_id,occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor_history ON audit_events(school_id,actor_user_id,occurred_at DESC);

-- Intendance hot paths.
CREATE INDEX IF NOT EXISTS idx_inventory_items_school_enabled_label ON inventory_items(school_id,enabled,label);
CREATE INDEX IF NOT EXISTS idx_inventory_assets_school_type_status ON inventory_assets(school_id,asset_type_id,status);
CREATE INDEX IF NOT EXISTS idx_inventory_asset_events_history ON inventory_asset_events(school_id,asset_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inventory_counts_school_created ON inventory_counts(school_id,created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inventory_count_lines_count ON inventory_count_lines(school_id,count_id,item_id);

-- Platform Manager System list/read paths.
CREATE INDEX IF NOT EXISTS idx_schools_status_name ON schools(status,lower(name),code);
CREATE INDEX IF NOT EXISTS idx_school_memberships_school_active ON school_memberships(school_id,active,user_id);
