# Point 3B Gate — Roles & Permissions

Status: **LOCAL IMPLEMENTATION COMPLETE — LIVE POSTGRES CERTIFICATION PENDING**

PASS conditions satisfied locally:
- all standard role baselines are explicit and owner-approved;
- no role capability references a missing catalog capability;
- section heads share one capability doctrine and use scopes;
- Promoteur/Gestionnaire cannot execute daily mutations by default;
- Caissier cannot view detailed peer cash sessions by default;
- Secretary is optional/minimal;
- Intendant has inventory capabilities without Finance;
- custom school roles remain supported;
- unit/static tests pass.

Live PostgreSQL/RLS and UI checkbox-tree behavior remain part of the final machine/VPS certification.
