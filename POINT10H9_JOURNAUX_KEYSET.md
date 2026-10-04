# Point 10H9 — Journaux volumineux / pagination keyset

- Audit transversal: keyset `(occurred_at,id)`, `limit+1`, `has_more`, `next_cursor`; suppression du COUNT systématique et des OFFSET profonds sur ce journal.
- Sync conflits/rejets: keyset `(received_at,id)`.
- Outbox pending: nouvel endpoint d'administration paginé par keyset `(created_at,id)`.
- PostgreSQL: index composites/partiels alignés exactement sur les ordres de parcours.
- Les listes administratives classiques conservent leur pagination offset bornée lorsque cela reste le meilleur compromis UX/coût.
- Certification de performance réelle reste conditionnée à PostgreSQL/Redis/k6 live avec EXPLAIN ANALYZE/BUFFERS et pg_stat_statements.
