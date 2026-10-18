"""Real-browser MFA enrolment probe (headless Chromium, the production frontend served by nginx of the staging stack).

Follows the owner's path exactly: first-run page → create the first Manager → sign in → enrolment screen →
read the key shown on screen and the otpauth link → "continue" → type the 6 digits in the code field.
It counts the /auth/mfa/enroll/start requests the page sends and checks that the key on screen is the key whose
code the server accepts. The secret, codes and tokens are never printed. Writes the account to CREDS_FILE (0600)
so the HTTP probe can reuse it after the harness resets the factor.
Usage: python3 mfa_browser_probe.py HOST PORT SETUP_TOKEN CREDS_FILE
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import struct
import sys
import time
import urllib.parse

from playwright.sync_api import sync_playwright

HOST, PORT, SETUP_TOKEN, CREDS = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
FAILS = 0


def result(ok: bool, label: str) -> None:
    global FAILS
    print(("PASS  " if ok else "FAIL  ") + label, flush=True)
    FAILS += 0 if ok else 1


def totp(secret_b32: str, step: int) -> str:
    key = base64.b32decode(secret_b32 + "=" * (-len(secret_b32) % 8))
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    return str((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1_000_000).zfill(6)


email = f"manager.navigateur.{secrets.token_hex(3)}@staging.edusync.test"
password = "Nav-" + secrets.token_urlsafe(18)
fd = os.open(CREDS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    json.dump({"email": email, "password": password}, f)

with sync_playwright() as p:
    browser = p.chromium.launch(args=[f"--host-resolver-rules=MAP {HOST}:80 127.0.0.1:{PORT}"])
    page = browser.new_page()
    starts, confirms, console_errors = [], [], []
    page.on("request", lambda r: starts.append(r.url) if r.url.endswith("/auth/mfa/enroll/start") else
            (confirms.append(r.url) if r.url.endswith("/auth/mfa/enroll/confirm") else None))
    page.on("console", lambda m: console_errors.append(m.text[:160]) if m.type == "error" else None)

    page.goto(f"http://{HOST}/", wait_until="domcontentloaded", timeout=60000)
    try:
        page.wait_for_selector("#su-name", timeout=60000)
    except Exception:
        print(f"      page : {page.url} — {(page.text_content('body') or '')[:300]}")
        raise
    page.fill("#su-name", "Manager Navigateur")
    page.fill("#su-email", email)
    page.fill("#su-pass", password)
    page.fill("#su-confirm", password)
    if page.locator("#su-token").count():
        page.fill("#su-token", SETUP_TOKEN)
    page.click("button.lg-submit")
    page.wait_for_selector("text=Manager Système créé", timeout=30000)
    result(True, "page d'installation : premier Manager créé dans le navigateur")

    page.fill("#lg-pass", password)
    page.click("button.lg-submit")
    page.wait_for_selector("img.mfa-qr", timeout=30000)
    page.wait_for_timeout(1500)                       # let any late re-render / duplicate request happen
    result(len(starts) == 1, f"écran d'enrôlement : une seule demande enroll/start ({len(starts)})")

    href = page.get_attribute("a.mfa-open", "href") or ""
    link_secret = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("secret", [""])[0]
    page.click("text=Impossible de scanner")
    shown = (page.text_content('code[aria-label="Clé de configuration"]') or "").replace(" ", "")
    result(bool(shown) and shown == link_secret, "clé affichée = clé du lien otpauth (et du QR)")
    title = page.text_content("#mfa-en-title") or ""
    issuer = urllib.parse.parse_qs(urllib.parse.urlparse(href).query).get("issuer", [""])[0]
    result(issuer == "EduSync", "émetteur affiché par l'application : EduSync")

    page.click("text=J’ai ajouté le compte, continuer")
    page.wait_for_selector("#mfa-first", timeout=10000)
    while time.time() % 30 > 25:
        time.sleep(0.5)
    page.locator("#mfa-first").press_sequentially(totp(shown, int(time.time() // 30)), delay=120)   # typed like a person
    try:
        page.wait_for_selector("text=Conservez vos codes de secours", timeout=15000)
        ok = True
    except Exception:
        ok = False
    error = (page.locator(".lg-error").text_content() if page.locator(".lg-error").count() else "") or ""
    result(ok, "code tapé dans le navigateur : enrôlement confirmé, codes de secours affichés" + (f" — erreur affichée : {error[:120]}" if error else ""))
    result(len(starts) == 1 and len(confirms) == 1, f"requêtes du navigateur : enroll/start={len(starts)}, enroll/confirm={len(confirms)}")
    result(len(page.locator(".mfa-codes li").all()) == 10 if ok else False, "10 codes de secours affichés")
    if console_errors:
        print("      console : " + " | ".join(console_errors[:5]))
    browser.close()

print(f"RÉSULTAT MFA NAVIGATEUR : {'PASS' if FAILS == 0 else f'FAIL ({FAILS})'}")
sys.exit(1 if FAILS else 0)
