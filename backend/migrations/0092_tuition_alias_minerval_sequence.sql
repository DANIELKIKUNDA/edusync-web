-- 2026-10-25 — owner report « on ne doit jamais sauter un mois impayé ».
-- The Web setup assistant names the monthly tuition « MINERVAL » while every finance rule expected the Desktop code
-- « SCOLARITE »: the monthly charges of Web-configured schools were generated with sequence_group 'NONE' (not
-- sequential), so a later month could be collected before an earlier unpaid one. The code now treats both codes as the
-- monthly tuition (edusync.shared.domain.fee_codes); this repairs the charges already generated. Data repair only:
-- amounts, payments and allocations are untouched; a month already paid stays paid.
UPDATE finance_charges fc
   SET sequence_group = 'MONTHLY:SCOLARITE', updated_at = now()
  FROM fee_types ft
 WHERE ft.id = fc.fee_type_id
   AND fc.periodicity = 'MONTHLY'
   AND COALESCE(fc.sequence_group, 'NONE') = 'NONE'
   AND (upper(ft.code) = 'MINERVAL' OR upper(ft.code) LIKE 'MINERVAL\_%');
