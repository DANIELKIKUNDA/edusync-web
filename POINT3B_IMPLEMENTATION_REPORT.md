# Point 3B — Implementation report — RBAC roles finalized

Date: 2026-09-12

## Result
The owner-approved role policy has been translated into exact capability bundles. The engine remains capability-based; job titles never bypass use-case invariants.

- Capability registry: 259 capabilities.
- Standard roles locked: 10 (1 platform + 9 school roles).
- Custom roles remain supported; `ASSISTANT_PROMOTEUR` is intentionally a custom blueprint, not a hardcoded standard role.
- `PREFET_ETUDES` and `DIRECTION_SECTION` share the exact same functional capability set. Their difference is label + assignment scope.
- Promoteur/Gestionnaire: governance readers, no daily execution.
- Caissier: operational finance/enrollment with own-cash ownership policy and audited payment reversal.
- Intendant: full inventory domain, no financial cash operations.

The migration `0008_owner_approved_school_roles.sql` creates/activates school-standard baselines and replaces their grants atomically at deployment level. Tenant schools customize through `SCHOOL_CUSTOM` clones instead of mutating product baselines.
