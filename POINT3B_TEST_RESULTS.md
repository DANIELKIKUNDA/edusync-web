# Point 3B — Test results

Date: 2026-09-12

- `pytest -q backend/tests`: **127 passed, 0 failed**
- `python -m compileall -q backend/src backend/tests`: **PASS**
- JSON contracts parse: **PASS**
- Standard roles locked: **10**
- Capability registry: **259** unique capabilities
- PostgreSQL migration added: `0008_owner_approved_school_roles.sql`

Verdict: **LOCAL PASS — live PostgreSQL/RLS/UI certification remains for the final machine/VPS gate.**
