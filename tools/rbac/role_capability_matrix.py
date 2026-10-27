"""Capability matrix of a standard role — static audit (level A), computed, never declared.

For each capability of the role in contracts/CAPABILITY_REGISTRY.json: lifecycle, the backend files that CHECK it
(need/require/permission tests), the frontend files that use it, the tests that mention it, and a status:
  PASS            ACTIVE, checked by the backend and covered by a test
  FAIL            ACTIVE but never checked by the backend (a right that guards nothing), or not covered by any test
  NOT APPLICABLE  ALIAS / DEPRECATED (resolved to its canonical capability) or PLANNED (feature not built, hidden)
Usage: python tools/rbac/role_capability_matrix.py GESTIONNAIRE [--markdown out.md]
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def files(base: Path, exts: tuple[str, ...]) -> dict[Path, str]:
    return {p: p.read_text(encoding="utf-8", errors="ignore") for p in base.rglob("*") if p.suffix in exts and "node_modules" not in p.parts and "__pycache__" not in p.parts}


def main() -> int:
    role = sys.argv[1] if len(sys.argv) > 1 else "GESTIONNAIRE"
    out = sys.argv[sys.argv.index("--markdown") + 1] if "--markdown" in sys.argv else None
    reg = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
    caps = {c["code"]: c for c in reg["capabilities"]}
    granted = sorted(reg["standard_roles"][role]["capabilities"])
    backend = files(ROOT / "backend/src", (".py", ".sql"))
    migrations = files(ROOT / "backend/migrations", (".sql",))
    frontend = files(ROOT / "frontend/src", (".ts", ".tsx"))
    tests = {**files(ROOT / "backend/tests", (".py",)), **files(ROOT / "frontend/tests", (".ts", ".tsx")), **files(ROOT / "frontend/browser-tests", (".ts", ".mjs"))}
    rows, counts = [], {"PASS": 0, "FAIL": 0, "NOT APPLICABLE": 0}
    for code in granted:
        c = caps.get(code, {}); life = c.get("lifecycle", "ABSENT")
        q = re.compile(r"['\"]" + re.escape(code) + r"['\"]")
        be = sorted(str(p.relative_to(ROOT)).replace("\\", "/") for p, s in backend.items() if q.search(s))
        fe = sorted(str(p.relative_to(ROOT / "frontend/src")).replace("\\", "/") for p, s in frontend.items() if q.search(s))
        te = sorted(p.name for p, s in tests.items() if q.search(s))
        if life in ("ALIAS", "DEPRECATED"):
            status, why = "NOT APPLICABLE", f"{life} → {c.get('alias_of') or c.get('replaced_by') or 'canonique'}"
        elif life == "PLANNED":
            status, why = "NOT APPLICABLE", "PLANNED : fonctionnalité non construite, masquée à l'écran"
        elif life != "ACTIVE":
            status, why = "FAIL", f"cycle de vie {life}"
        elif not be:
            status, why = "FAIL", "aucun contrôle serveur : le droit ne protège rien"
        elif not te:
            status, why = "FAIL", "aucun test ne le couvre"
        else:
            status, why = "PASS", "" if fe else "API seulement (pas d'écran dédié)"
        counts[status] += 1
        rows.append((code, life, be, fe, te, status, why))
    lines = [f"Rôle {role} : {len(granted)} capacités — " + " · ".join(f"{k} {v}" for k, v in counts.items()), "",
             "| Capacité | Cycle | Backend (contrôle) | Frontend | Tests | Résultat |", "|---|---|---|---|---|---|"]
    for code, life, be, fe, te, status, why in rows:
        short = lambda xs: (", ".join(Path(x).name for x in xs[:2]) + (f" +{len(xs) - 2}" if len(xs) > 2 else "")) or "—"
        lines.append(f"| `{code}` | {life} | {short(be)} | {short(fe)} | {len(te) or '—'} | **{status}**{(' — ' + why) if why else ''} |")
    text = "\n".join(lines)
    if out:
        Path(out).write_text(text + "\n", encoding="utf-8")
    print(lines[0])
    for code, life, be, fe, te, status, why in rows:
        if status == "FAIL":
            print(f"  FAIL {code} ({life}) — {why}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
