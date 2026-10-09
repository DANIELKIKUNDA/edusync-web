"""Supply chain check (hardening J, 2026-10): lockfiles, licences, SBOM (CycloneDX 1.5).

    python tools/certification/supply_chain.py

Reads only local files: backend/requirements.lock + installed metadata, frontend/package-lock.json.
Writes certification/n0-n1-20261007/sbom.cdx.json and supply-chain.json. Vulnerability scans are separate
(npm audit, pip-audit) because they need the network.
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "certification" / "n0-n1-20261007"
PERMISSIVE = re.compile(r"\b(MIT|BSD|Apache|ISC|PSF|Python|0BSD|Unlicense|CC0|BlueOak|Zlib|MPL|HPND|Historical Permission|OFL)\b", re.I)
COPYLEFT = re.compile(r"\b(A?GPL|SSPL|EUPL|CC-BY-SA|OSL)\b", re.I)


def py_license(dist: metadata.Distribution) -> str:
    m = dist.metadata
    expr = m.get("License-Expression")
    if expr:
        return expr
    classifiers = [c.split("::")[-1].strip() for c in m.get_all("Classifier") or [] if c.startswith("License ::")]
    if classifiers:
        return " / ".join(sorted(set(classifiers)))
    lic = (m.get("License") or "").strip()
    return lic.splitlines()[0][:80] if lic else "INCONNUE"


def classify(lic: str) -> str:
    if lic == "INCONNUE":
        return "A_VERIFIER"
    if COPYLEFT.search(lic) and not re.search(r"\bLGPL\b", lic, re.I):
        return "COPYLEFT_A_EXAMINER"
    if re.search(r"\bLGPL\b", lic, re.I):
        return "LGPL_LIAISON_DYNAMIQUE"
    return "PERMISSIVE" if PERMISSIVE.search(lic) else "A_VERIFIER"


def main() -> None:
    components, report = [], {"python": [], "npm": [], "lockfiles": {}}
    lock = ROOT / "backend" / "requirements.lock"
    report["lockfiles"]["backend/requirements.lock"] = lock.exists()
    report["lockfiles"]["frontend/package-lock.json"] = (ROOT / "frontend" / "package-lock.json").exists()
    for line in lock.read_text(encoding="ascii").splitlines():
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==")
        try:
            lic = py_license(metadata.distribution(name))
        except metadata.PackageNotFoundError:
            lic = "INCONNUE"
        report["python"].append({"name": name, "version": version, "license": lic, "class": classify(lic)})
        components.append({"type": "library", "name": name, "version": version, "purl": f"pkg:pypi/{name.lower()}@{version}",
                           "licenses": [{"expression": lic}] if lic != "INCONNUE" else []})
    pkg = json.loads((ROOT / "frontend" / "package-lock.json").read_text(encoding="utf-8"))
    for path, info in pkg.get("packages", {}).items():
        if not path or info.get("dev"):
            continue  # root package and build-only tooling are not shipped to browsers
        name = path.split("node_modules/")[-1]
        lic = info.get("license") or "INCONNUE"
        report["npm"].append({"name": name, "version": info.get("version"), "license": lic, "class": classify(lic)})
        components.append({"type": "library", "name": name, "version": info.get("version"), "purl": f"pkg:npm/{name}@{info.get('version')}",
                           "licenses": [{"expression": lic}] if lic != "INCONNUE" else []})
    sbom = {"bomFormat": "CycloneDX", "specVersion": "1.5", "serialNumber": f"urn:uuid:{uuid.uuid4()}", "version": 1,
            "metadata": {"timestamp": datetime.now(timezone.utc).isoformat(), "component": {"type": "application", "name": "edusync-web", "version": "0.52.0"}},
            "components": components}
    (OUT / "sbom.cdx.json").write_text(json.dumps(sbom, indent=1, ensure_ascii=False), encoding="utf-8")
    flagged = [x for x in report["python"] + report["npm"] if x["class"] != "PERMISSIVE"]
    report["summary"] = {"python": len(report["python"]), "npm_runtime": len(report["npm"]), "flagged": flagged}
    (OUT / "supply-chain.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"Python : {len(report['python'])} paquets · npm (exécution) : {len(report['npm'])} · à examiner : {len(flagged)}")
    for x in flagged:
        print(f"  {x['class']:<24} {x['name']} {x['version']} — {x['license']}")


if __name__ == "__main__":
    main()
