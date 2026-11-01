-- Saving a rule of a DRAFT exigibility policy replaces its day bands (PostgresAnnualPolicyAdminRepository.put_rule:
-- DELETE then INSERT). 0105 revoked DELETE from the tenant role on every MEF table to protect history, so saving a rule
-- failed with « droit refusé pour la table finance_exigibility_day_bands » (found 2026-11-01, first real school APN).
-- The tenant may now delete day bands ONLY when their policy is still a DRAFT; the bands of an ACTIVE or SUPERSEDED
-- policy stay immutable (a restrictive policy filters them out of any DELETE). Every other MEF table keeps no DELETE.
GRANT DELETE ON finance_exigibility_day_bands TO edusync_tenant;

DROP POLICY IF EXISTS finance_exigibility_day_bands_draft_delete ON finance_exigibility_day_bands;
CREATE POLICY finance_exigibility_day_bands_draft_delete ON finance_exigibility_day_bands
  AS RESTRICTIVE FOR DELETE
  USING (EXISTS (
    SELECT 1 FROM finance_exigibility_rules r
      JOIN finance_exigibility_policies p ON p.id = r.policy_id AND p.school_id = r.school_id
     WHERE r.id = finance_exigibility_day_bands.rule_id
       AND r.school_id = finance_exigibility_day_bands.school_id
       AND p.status = 'DRAFT'
  ));
