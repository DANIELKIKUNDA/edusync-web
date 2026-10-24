"""Platform member activation from an invitation opened in the installed Android PWA (fix 2026-10-24).

Root cause (reproduced on the deployed version: boot screen still shown after 25 s, no API call, member PENDING):
App's session restoration returned early when the address held #invitation=… WITHOUT ending `restoring`, while the
token was only read by the sign-in screen, which is mounted after `restoring` ends. Endless boot screen.
Fix: the link is read by main.tsx before anything else and handed to App, restoration is skipped but the boot screen
released, a static safety net replaces any boot screen still visible after 15 s, an already-open PWA receives links
through hashchange, the platform invitation sets a password (owner: platform = e-mail + password + 6-digit code).
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
F = ROOT / "frontend"
APP = (F / "src/App.tsx").read_text(encoding="utf-8")
MAIN = (F / "src/main.tsx").read_text(encoding="utf-8")
LINKS = (F / "src/account_links.tsx").read_text(encoding="utf-8")
LOGIN = (F / "src/login.tsx").read_text(encoding="utf-8")
INDEX = (F / "index.html").read_text(encoding="utf-8")
SW = (F / "public/sw.js").read_text(encoding="utf-8")
FALLBACK = (F / "public/boot-fallback.js").read_text(encoding="utf-8")
IAM = (ROOT / "backend/src/edusync/modules/iam/api/router.py").read_text(encoding="utf-8")


def test_link_is_read_before_session_restoration_and_reaches_the_screen():
    assert "const initialLink=takeAccountLink();" in MAIN and "<App initialLink={initialLink}/>" in MAIN
    assert "export function App({initialLink=null}" in APP
    assert "initialLink={pendingLink}" in APP and "initialLink?:AccountLink|null" in LOGIN


def test_restoration_never_returns_without_releasing_the_boot_screen():
    restore = APP.split("async function restore(){", 1)[1].split("const online=", 1)[0]
    assert "#(reset|invitation)=" not in restore                       # the endless early return is gone
    assert "if(initialLink){if(alive)setRestoring(false);return}" in restore
    assert "ctl.abort(),10000" in restore and "signal:ctl.signal" in restore      # no endless wait for /auth/refresh


def test_already_open_pwa_receives_links():
    assert "window.addEventListener('hashchange',h)" in APP
    manifest = json.loads((F / "public/manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["scope"] == "/" and manifest["start_url"] == "/"
    assert manifest["launch_handler"]["client_mode"][0] == "navigate-existing"


def test_boot_screen_safety_net_is_served_and_cached():
    assert '<script src="/boot-fallback.js" defer></script>' in INDEX
    assert "BOOT_LIMIT_MS = 15000" in FALLBACK and "Réessayer" in FALLBACK and "location.reload()" in FALLBACK
    assert "'/boot-fallback.js'" in SW.split("const SHELL=", 1)[1].split(";", 1)[0]
    assert "token" not in FALLBACK.split("console.info", 1)[1].split(";", 1)[0]


def test_platform_invitation_keeps_password_then_six_digit_code():
    assert "Continuer sans mot de passe" not in LINKS and "activate-platform" not in LINKS
    assert "{inv && <PasswordPair" in LINKS
    assert "if(email)setValue('email',email)" in LOGIN


def test_backend_inspects_without_token_in_url_and_returns_the_address():
    inspect = IAM.split('@router.post("/invitations/inspect")', 1)[1].split("@router.", 1)[0]
    assert "body.token" in inspect and "_assert_same_origin" in inspect and "NEUTRAL_REFUSAL" in inspect
    accept = IAM.split('@router.post("/invitations/accept")', 1)[1].split("@router.", 1)[0]
    assert '"email": email' in accept and "account_links.consume" in accept
    assert "token" not in "".join(l for l in IAM.splitlines() if "log.info(\"invitation." in l).replace("tokens", "")
