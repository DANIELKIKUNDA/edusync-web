-- Owner decision 2026-10-28 (certification Responsable financier, tableau de bord): « il faut aussi les cartes des
-- effectifs, total et par section ». The Responsable chargé des finances READS the headcounts — total, girls / boys and
-- per section — to relate the number of pupils to the amounts expected. Read only: no movement, export or class detail.
-- Additive grant; each capability stays school-adjustable (Accès & rôles).
INSERT INTO rbac_role_capabilities(role_id, capability_code)
SELECT r.id, c FROM rbac_roles r, unnest(ARRAY['headcounts.read','headcounts.by_section.read']::varchar[]) c
 WHERE r.code = 'RESPONSABLE_FINANCE' AND r.kind = 'SCHOOL_STANDARD' AND r.school_id IS NULL
ON CONFLICT DO NOTHING;
