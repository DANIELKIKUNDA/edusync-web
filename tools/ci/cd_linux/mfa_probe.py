"""Live MFA/TOTP enrolment probe against a running EduSync (staging harness): real HTTP through nginx, real cookies.

  first Manager (setup token) → platform login → enrol/start (QR + secret) → wrong code / expired code refused →
  valid code computed from the secret → enrol/confirm with the same step token → session + Secure cookie →
  sign-in again → verify: rate limit does not mask a valid code before the limit, locks after it.

The TOTP is computed here independently of the application code (RFC 6238, SHA-1, 6 digits, 30 s, Unix time).
The secret, the codes and the tokens are NEVER printed. Standard library only.
Usage: python3 mfa_probe.py BASE_URL HOST ORIGIN SETUP_TOKEN
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import http.cookiejar
import json
import secrets
import struct
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE, HOST, ORIGIN, SETUP_TOKEN = sys.argv[1:5]
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


class Client:
    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.set_cookies: list[str] = []

    def post(self, path: str, body: dict) -> tuple[int, dict]:
        req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), method="POST",
                                     headers={"Host": HOST, "Origin": ORIGIN, "Content-Type": "application/json", "X-Forwarded-Proto": "https"})
        try:
            with self.opener.open(req, timeout=30) as r:
                self.set_cookies += r.headers.get_all("Set-Cookie") or []
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except ValueError:
                return e.code, {}

    def get(self, path: str) -> tuple[int, dict]:
        req = urllib.request.Request(BASE + path, headers={"Host": HOST})
        try:
            with self.opener.open(req, timeout=30) as r:
                return r.status, json.loads(r.read() or b"{}")
        except urllib.error.HTTPError as e:
            return e.code, {}


def wait_next_step_margin() -> None:
    """Avoid computing a code in the last 3 seconds of its 30 s window."""
    while time.time() % 30 > 27:
        time.sleep(0.5)


email = f"manager.mfa.{secrets.token_hex(3)}@staging.edusync.test"
password = "Mfa-" + secrets.token_urlsafe(18)
c = Client()

with urllib.request.urlopen(urllib.request.Request(BASE + "/health-api", headers={"Host": HOST}), timeout=30) as r:
    import email.utils
    skew = email.utils.parsedate_to_datetime(r.headers["Date"]).timestamp() - time.time()
print(f"      écart d'horloge serveur/sonde : {skew:+.1f} s (TOTP : temps Unix)")
code, st = c.get("/api/v1/setup/status")
result(code == 200 and st.get("setup_required") is True, "installation vierge : création du premier Manager disponible")
code, body = c.post("/api/v1/setup/first-manager", {"full_name": "Manager MFA", "email": email, "password": password, "setup_token": SETUP_TOKEN})
result(code == 201, f"premier Manager créé ({code})")

code, step = c.post("/api/v1/auth/login", {"email": email, "password": password, "scope": "PLATFORM"})
result(code == 200 and step.get("mfa_enrollment_required") is True and not c.set_cookies, "connexion : étape d'enrôlement, aucune session ni cookie avant le second facteur")
token = step.get("mfa_token", "")

code, enrol = c.post("/api/v1/auth/mfa/enroll/start", {"mfa_token": token})
result(code == 200, f"enrôlement démarré ({code})")
secret = enrol.get("secret", "")
uri = urllib.parse.urlparse(enrol.get("otpauth_uri", ""))
q = urllib.parse.parse_qs(uri.query)
label = urllib.parse.unquote(uri.path.lstrip("/"))
result(q.get("secret") == [secret] and len(secret) == 32, "le QR (otpauth) contient exactement le secret de l'enrôlement")
result(q.get("algorithm") == ["SHA1"] and q.get("digits") == ["6"] and q.get("period") == ["30"], "profil TOTP standard : SHA1, 6 chiffres, 30 s")
result(q.get("issuer") == ["EduSync"] and label == f"EduSync:{email}" and enrol.get("issuer") == "EduSync", "émetteur et libellé : EduSync")
result("Atelier Pro" not in json.dumps({k: v for k, v in enrol.items() if k not in ("secret", "qr_svg")}), "aucune mention « Atelier Pro » dans l'enrôlement")

now_step = int(time.time() // 30)
wrong = str((int(totp(secret, now_step)) + 1) % 1_000_000).zfill(6)
code, err = c.post("/api/v1/auth/mfa/enroll/confirm", {"mfa_token": token, "code": wrong})
result(code == 400 and "incorrect" in err.get("detail", ""), f"mauvais code refusé ({code})")
code, err = c.post("/api/v1/auth/mfa/enroll/confirm", {"mfa_token": token, "code": totp(secret, now_step - 3)})
result(code == 400, f"code expiré (90 s) refusé ({code})")

wait_next_step_margin()
code, session = c.post("/api/v1/auth/mfa/enroll/confirm", {"mfa_token": token, "code": totp(secret, int(time.time() // 30))})
result(code == 200 and session.get("access_token") and len(session.get("recovery_codes", [])) == 10,
       f"code valide calculé depuis le secret : enrôlement confirmé, session ouverte, 10 codes de secours ({code})")
refresh = [h for h in c.set_cookies if "refresh" in h.lower() or "session" in h.lower()]
flags = refresh[0].lower() if refresh else ""
result(bool(refresh) and "secure" in flags and "httponly" in flags and "samesite" in flags,
       "cookie de session : Secure, HttpOnly, SameSite")
result("domain=" not in flags, "cookie lié à l'hôte (aucun attribut Domain)")
code, me = c.post("/api/v1/auth/mfa/enroll/confirm", {"mfa_token": token, "code": totp(secret, int(time.time() // 30))})
result(code in (400, 401), f"jeton d'étape à usage unique : rejeu refusé ({code})")

# Sign-in again: second factor required; failures below the limit never mask a later valid code.
c2 = Client()
code, step2 = c2.post("/api/v1/auth/login", {"email": email, "password": password, "scope": "PLATFORM"})
result(code == 200 and step2.get("mfa_required") is True, "nouvelle connexion : code demandé")
t2 = step2.get("mfa_token", "")
for _ in range(2):
    c2.post("/api/v1/auth/mfa/verify", {"mfa_token": t2, "code": "000000" if totp(secret, int(time.time() // 30)) != "000000" else "111111"})
time.sleep(31)                                    # the enrolment code's step was used: wait for a fresh step
wait_next_step_margin()
code, ok = c2.post("/api/v1/auth/mfa/verify", {"mfa_token": t2, "code": totp(secret, int(time.time() // 30))})
result(code == 200 and ok.get("access_token"), f"après 2 erreurs, un code valide est accepté (limite non atteinte) ({code})")

c3 = Client()
code, step3 = c3.post("/api/v1/auth/login", {"email": email, "password": password, "scope": "PLATFORM"})
t3 = step3.get("mfa_token", "")
codes = [c3.post("/api/v1/auth/mfa/verify", {"mfa_token": t3, "code": "000000"})[0] for _ in range(8)]
result(429 in codes or 401 in codes, f"au-delà de la limite : verrouillage ({codes})")

print(f"RÉSULTAT MFA : {'PASS' if FAILS == 0 else f'FAIL ({FAILS})'}")
sys.exit(1 if FAILS else 0)
