-- N3-E / G-FIN-1 — Desktop finance_checkout._validate_allocations: only the monthly tuition (SCOLARITE family) and the
-- tranches are sequential. The Web chained every monthly fee (MONTHLY:<code>). Sequence metadata of the monthly charges is
-- realigned on the fee type; no amount, no payment and no allocation is touched.
UPDATE finance_charges fc
   SET sequence_group = CASE WHEN upper(ft.code) = 'SCOLARITE' OR upper(ft.code) LIKE 'SCOLARITE\_%' THEN 'MONTHLY:SCOLARITE' ELSE 'NONE' END
  FROM fee_types ft
 WHERE ft.id = fc.fee_type_id AND fc.periodicity = 'MONTHLY'
   AND fc.sequence_group IS DISTINCT FROM (CASE WHEN upper(ft.code) = 'SCOLARITE' OR upper(ft.code) LIKE 'SCOLARITE\_%' THEN 'MONTHLY:SCOLARITE' ELSE 'NONE' END);
