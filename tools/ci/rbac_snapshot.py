"""Snapshot of the EFFECTIVE permissions of every active school membership (RBAC migration proof, owner decision 12).

    python tools/ci/rbac_snapshot.py snapshot OUT.json [--legacy]   # owner database URL from EDUSYNC_OWNER_DATABASE_URL
    python tools/ci/rbac_snapshot.py compare BEFORE.json AFTER.json

The snapshot goes through the application's own code (PostgresMembershipRepository.permissions and
PostgresAuthorizationRepository.effective_capability_grants), so the "after" run proves what the engine really grants.
`compare` canonicalizes the export format aliases of contracts/CAPABILITY_REGISTRY.json (a variant and its
`*.export` capability are the same authorization) and fails on any other difference. No personal data: ids only.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))


# Pre-0085 engine, copied verbatim from the code it replaces (memberships.permissions and
# effective_capability_grants before 2026-10-23): used to take the BEFORE snapshot on a database not yet migrated.
LEGACY_PERMISSIONS = """
    SELECT DISTINCT capability_code FROM (
        SELECT rc.capability_code FROM rbac_assignments a
          JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
          JOIN rbac_role_capabilities rc ON rc.role_id=r.id
         WHERE a.membership_id=:mid AND a.active=true AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
        UNION
        SELECT eg.capability_code FROM rbac_exception_grants eg
         WHERE eg.membership_id=:mid AND eg.active=true AND eg.valid_from<=now() AND eg.valid_until>now()
    ) q ORDER BY capability_code"""
LEGACY_GRANTS = """
    SELECT DISTINCT rc.capability_code, s.scope_type, s.scope_value FROM rbac_assignments a
      JOIN rbac_roles r ON r.id=a.role_id AND r.status='ACTIVE'
      JOIN rbac_role_capabilities rc ON rc.role_id=r.id
      JOIN rbac_assignment_scopes s ON s.assignment_id=a.id
     WHERE a.user_id=:uid AND a.school_id=:sid AND a.active=true AND a.valid_from<=now() AND (a.valid_until IS NULL OR a.valid_until>now())
    UNION
    SELECT eg.capability_code,eg.scope_type,eg.scope_value FROM rbac_exception_grants eg
     WHERE eg.user_id=:uid AND eg.school_id=:sid AND eg.active=true AND eg.valid_from<=now() AND eg.valid_until>now()"""


def snapshot(out: str, legacy: bool = False) -> None:
    from sqlalchemy import create_engine, text
    from edusync.adapters.postgres_authorization import PostgresAuthorizationRepository
    from edusync.adapters.postgres_repositories import PostgresMembershipRepository
    engine = create_engine(os.environ["EDUSYNC_OWNER_DATABASE_URL"])
    result = {}
    with engine.begin() as c:
        rows = c.execute(text("""SELECT m.id, m.user_id, m.school_id FROM school_memberships m
            WHERE m.active AND EXISTS (SELECT 1 FROM rbac_assignments a WHERE a.membership_id=m.id AND a.active) ORDER BY m.id""")).all()
        for mid, uid, sid in rows:
            if legacy:
                perms = sorted(str(r[0]) for r in c.execute(text(LEGACY_PERMISSIONS), {"mid": mid}))
                triples = c.execute(text(LEGACY_GRANTS), {"uid": uid, "sid": sid}).all()
            else:
                perms = sorted(PostgresMembershipRepository(c).permissions(mid))
                triples = PostgresAuthorizationRepository(c).effective_capability_grants(uid, sid)
            grants = sorted({f"{cap}|{st}|{sv or ''}" for cap, st, sv in triples})
            result[str(mid)] = {"permissions": perms, "scoped": grants}
    Path(out).write_text(json.dumps(result, indent=0, sort_keys=True), encoding="utf-8")
    print(f"snapshot: {len(result)} memberships -> {out}")


def _aliases() -> dict[str, str]:
    reg = json.loads((ROOT / "contracts" / "CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
    return {c["code"]: c["alias_of"] for c in reg["capabilities"] if c.get("alias_of")}


def _canon(codes, aliases):
    out = set()
    for code in codes:
        cap, sep, rest = code.partition("|")
        out.add(aliases.get(cap, cap) + sep + rest)
    return out


def compare(before: str, after: str) -> int:
    a = json.loads(Path(before).read_text(encoding="utf-8"))
    b = json.loads(Path(after).read_text(encoding="utf-8"))
    aliases = _aliases()
    bad = 0
    if set(a) != set(b):
        print("memberships differ:", sorted(set(a) ^ set(b)))
        bad += 1
    raw_changes = 0
    for mid in sorted(set(a) & set(b)):
        for key in ("permissions", "scoped"):
            x, y = set(a[mid][key]), set(b[mid][key])
            if x != y:
                raw_changes += 1
            if _canon(x, aliases) != _canon(y, aliases):
                bad += 1
                print(f"{mid} {key}: lost {sorted(_canon(x, aliases) - _canon(y, aliases))} gained {sorted(_canon(y, aliases) - _canon(x, aliases))}")
    print(f"compared {len(a)} memberships: {bad} difference(s) after alias canonicalization; {raw_changes} raw set(s) differ only by aliases")
    return 1 if bad else 0


if __name__ == "__main__":
    if sys.argv[1] == "snapshot":
        snapshot(sys.argv[2], legacy="--legacy" in sys.argv)
    else:
        sys.exit(compare(sys.argv[2], sys.argv[3]))
