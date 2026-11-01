"""Release version of EduSync (Semantic Versioning, owner 2026-11-01).

Single source for the backend: backend/pyproject.toml (PEP 440 form, e.g. 1.0.0rc1 for 1.0.0-rc.1). The repository VERSION
file, frontend/package.json and this value are kept equal by backend/tests/test_release_version.py.
"""
from __future__ import annotations

import re
from importlib import metadata
from pathlib import Path


def _read() -> str:
    try:
        return metadata.version("edusync-web-backend")
    except metadata.PackageNotFoundError:  # source checkout (PYTHONPATH=src): read pyproject.toml
        pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
        try:
            found = re.search(r'^version\s*=\s*"([^"]+)"', pyproject.read_text(encoding="utf-8"), re.M)
            return found.group(1) if found else "0.0.0"
        except OSError:
            return "0.0.0"


def semver(pep440: str) -> str:
    """1.0.0rc1 → 1.0.0-rc.1 (the form shown to users); a final release is unchanged."""
    m = re.fullmatch(r"(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?", pep440)
    if not m:
        return pep440
    base, tag, n = m.groups()
    if not tag:
        return base
    return f"{base}-{ {'a': 'alpha', 'b': 'beta', 'rc': 'rc'}[tag] }.{n}"


APP_VERSION = semver(_read())
