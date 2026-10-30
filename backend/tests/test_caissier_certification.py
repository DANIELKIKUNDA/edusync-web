"""Cashier certification (2026-10-24), real cashier day on the local stack (frontend/browser-tests/
local_caissier_certification.mjs). Fixed while certifying:
- the receipt preview (PDF built in the browser, blob: URL, shown in an iframe) was blocked by the CSP everywhere
  (no frame-src → default-src 'self'): frame-src 'self' blob: only, in production nginx and the local preview;
- the setup journey and « Compléter le paramétrage » only for whoever can change the settings, not a cashier;
- Personnel no longer shows endless metric skeletons to a role without personnel.summary.read.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NGINX = (ROOT / "frontend/nginx.conf").read_text(encoding="utf-8")
LOCAL = (ROOT / "tools/local/edusync_local.py").read_text(encoding="utf-8")
PROJECTION = (ROOT / "backend/src/edusync/modules/access/application/projection.py").read_text(encoding="utf-8")
PERSONNEL = (ROOT / "frontend/src/personnel.tsx").read_text(encoding="utf-8")


def test_receipt_preview_frames_are_allowed_but_only_same_origin_and_blob():
    for csp in [l for l in NGINX.splitlines() if "Content-Security-Policy" in l]:
        assert "frame-src 'self' blob:;" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert NGINX.count("frame-src 'self' blob:;") == 2
    local = LOCAL.split('"Content-Security-Policy":', 1)[1].split('"X-Content-Type-Options"', 1)[0]   # multi-line string
    assert "frame-src 'self' blob:;" in local and "frame-ancestors 'none'" in local


def test_setup_widgets_need_a_settings_manager():
    for wid in ('"settings.readiness"', '"settings.open"'):
        line = next(l for l in PROJECTION.splitlines() if wid in l)
        assert '"settings.school_identity.update"' in line


def test_personnel_never_waits_for_a_summary_it_cannot_read():
    assert "(summary||can('personnel.summary.read'))&&<div className=\"personMetrics\">" in PERSONNEL
    # PR #27: a profile without personnel.read opens on the functions tab instead of an empty directory.
    assert "permissions.includes('personnel.summary.read')?'overview':permissions.includes('personnel.read')?'directory':'functions'" in PERSONNEL


def test_each_role_has_its_own_home():
    """Owner 2026-10-24: « chaque rôle doit avoir son propre tableau de bord ». Administration cards need a management
    right (a cashier only reads the year / structure through the secretariat baseline); the desk has its own cards."""
    import json
    from edusync.modules.access.application.projection import WIDGETS, ACTIONS, _allowed
    reg = json.loads((ROOT / "contracts/CAPABILITY_REGISTRY.json").read_text(encoding="utf-8"))
    roles = reg["standard_roles"]
    def home(role):
        caps = set(roles[role]["capabilities"])
        return {w["id"] for w in WIDGETS if _allowed(w, caps)}, {a["id"] for a in ACTIONS if _allowed(a, caps)}
    cash_w, cash_a = home("CAISSIER"); admin_w, _ = home("ADMIN_SYSTEME_ECOLE")
    assert {"cash.today", "cash.receipts", "enrollments.today", "products.watch"} <= cash_w
    assert not ({"settings.readiness", "settings.academic_year", "settings.structure", "sync.devices", "access.members"} & cash_w)
    assert {"checkout.new", "enrollments.new"} <= cash_a and "settings.open" not in cash_a
    assert {"settings.readiness", "settings.academic_year", "settings.structure", "sync.devices", "access.members"} <= admin_w
    assert cash_w != admin_w
