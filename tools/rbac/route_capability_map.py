"""Route ↔ capability map for given standard roles (certification Intendant / Directeur des études / Directeur de discipline,
2026-10-30). Introspects the REAL FastAPI application (every included router, with its prefix) and, for each capability
of the roles, lists the routes whose endpoint CHECKS it (need / require / _need* / scope-aware guards, or
required_capability of an archived document). A textual mention elsewhere is not counted.

Usage: python tools/rbac/route_capability_map.py ROLE [ROLE ...] [--json out.json]
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from fastapi.routing import APIRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from edusync.bootstrap.app import create_app  # noqa: E402

GUARD = r"(?:need|require|_need[a-z_]*|_require[a-z_]*|scopes_for|_scopes)\(\s*(?:actor\s*,\s*|a\s*,\s*)?['\"]{cap}['\"]"


def routes():
    app = create_app()
    with TestClient(app):
        pass
    out = []

    def walk(rs, prefix=""):
        for r in rs:
            if isinstance(r, APIRoute):
                out.append((prefix + r.path, sorted(r.methods - {"HEAD", "OPTIONS"}), r))
            elif type(r).__name__ == "_IncludedRouter":
                walk(r.original_router.routes, prefix + (getattr(r.include_context, "prefix", "") or ""))
    walk(app.routes)
    return out


def main(argv: list[str]) -> int:
    out_json = None
    if "--json" in argv:
        i = argv.index("--json"); out_json = argv[i + 1]; argv = argv[:i] + argv[i + 2:]
    reg = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
    cat = {c["code"]: c for c in reg["capabilities"]}
    rs = routes()
    sources = []
    for path, methods, r in rs:
        try:
            sources.append((path, methods, r, inspect.getsource(r.endpoint)))
        except (OSError, TypeError):
            pass
    result = {}
    for role in argv:
        rows = []
        for cap in sorted(reg["standard_roles"][role]["capabilities"]):
            c = cat.get(cap, {})
            pat = re.compile(GUARD.format(cap=re.escape(cap)))
            hits = [f"{'/'.join(m)} {p}" for p, m, _, src in sources if pat.search(src)]
            rows.append({"capability": cap, "lifecycle": c.get("lifecycle"), "alias_of": c.get("alias_of"), "routes": hits})
        result[role] = rows
        print(f"\n== {role} ({len(rows)})")
        for row in rows:
            print(f"{row['lifecycle']:<10} {row['capability']:<38} {'; '.join(row['routes'][:3]) or ('→ ' + row['alias_of'] if row['alias_of'] else '— aucune route')}")
    if out_json:
        Path(out_json).write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
