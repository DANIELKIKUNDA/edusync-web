-- MEF fix (2026-11-02, owner report « Le serveur n'a pas pu enregistrer » on « Configurer ») : saving a rule replaces
-- its day bands (DELETE then INSERT), but 0105 revoked DELETE from edusync_tenant on every MEF table, so the very first
-- rule of a draft failed with « permission denied for table finance_exigibility_day_bands ».
-- Least privilege kept: the tenant may delete day bands ONLY when their rule belongs to a DRAFT policy of its own
-- school (RESTRICTIVE policy, combined with the tenant policy of 0105). Bands of an ACTIVE or SUPERSEDED policy stay
-- immutable; nothing else gains DELETE.
GRANT DELETE ON finance_exigibility_day_bands TO edusync_tenant;
DROP POLICY IF EXISTS finance_exigibility_day_bands_draft_delete ON finance_exigibility_day_bands;
CREATE POLICY finance_exigibility_day_bands_draft_delete ON finance_exigibility_day_bands
  AS RESTRICTIVE FOR DELETE
  USING (EXISTS (
    SELECT 1
      FROM finance_exigibility_rules r
      JOIN finance_exigibility_policies p ON p.id = r.policy_id AND p.school_id = r.school_id
     WHERE r.id = finance_exigibility_day_bands.rule_id
       AND r.school_id = finance_exigibility_day_bands.school_id
       AND p.status = 'DRAFT'));
