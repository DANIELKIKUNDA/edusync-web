"""Release version (owner, 2026-11-01): EduSync carries a standard version, Semantic Versioning MAJOR.MINOR.PATCH
(with an optional pre-release such as -rc.1), instead of showing a commit code to users. One value, everywhere."""
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-(alpha|beta|rc)\.(0|[1-9]\d*))?$")


def version() -> str:
    return (ROOT / "VERSION").read_text(encoding="utf-8").strip()


def test_version_is_semantic():
    assert SEMVER.match(version()), version()


def test_frontend_backend_and_lockfile_carry_the_same_version():
    from edusync.version import APP_VERSION, semver
    v = version()
    assert json.loads((ROOT / "frontend/package.json").read_text(encoding="utf-8"))["version"] == v
    lock = json.loads((ROOT / "frontend/package-lock.json").read_text(encoding="utf-8"))
    assert lock["version"] == v and lock["packages"][""]["version"] == v
    pyproject = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "backend/pyproject.toml").read_text(encoding="utf-8"), re.M).group(1)
    assert semver(pyproject) == v and APP_VERSION == v


def test_version_reaches_users_and_the_changelog():
    vite = (ROOT / "frontend/vite.config.ts").read_text(encoding="utf-8")
    assert "__EDUSYNC_VERSION__" in vite and "version: VERSION" in vite          # compiled in and published in /version.json
    up = (ROOT / "frontend/src/platform/updates.ts").read_text(encoding="utf-8")
    assert "Version ${CURRENT_VERSION} installée" in up
    assert "{CURRENT_VERSION}" in (ROOT / "frontend/src/platform/account.tsx").read_text(encoding="utf-8")
    assert f"## [{version()}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_a_release_tag_must_match_the_version_file():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert 'refs/tags/v' in ci and "cat VERSION" in ci
