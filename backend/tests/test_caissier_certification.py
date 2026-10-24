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
    assert "permissions.includes('personnel.summary.read')?'overview':'directory'" in PERSONNEL
