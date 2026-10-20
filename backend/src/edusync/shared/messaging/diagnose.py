"""Configuration diagnosis of the messaging providers — variable NAMES and outcomes only, never a value.

Used by the worker snapshot (what the sending process really sees), by the cockpit (what the API sees) and from a
shell inside a container (read-only proof on a server):

    docker compose … exec -T communications-worker python -m edusync.shared.messaging.diagnose worker
    docker compose … exec -T backend               python -m edusync.shared.messaging.diagnose api

Each check: {"name": <variable or fact>, "ok": bool | None, "detail": <sanitized French explanation>}.
The Firebase service account may be given as a file (mounted inside the container), as JSON, or as base64 JSON in
EDUSYNC_FCM_SERVICE_ACCOUNT_JSON (the safest form for an env file: one line, no quoting issue).
"""
from __future__ import annotations

import base64
import binascii
import json
import os
import re
import sys

EMAIL_RX = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
REQUIRED_SA = ("type", "project_id", "private_key", "client_email")


class CredentialError(RuntimeError):
    def __init__(self, code: str, detail: str):
        super().__init__(code)
        self.code, self.detail = code, detail


def load_service_account(file_path: str, raw_json: str) -> dict:
    """The service account as a dict, from JSON, base64 JSON or a file. Raises CredentialError (code + detail, no value)."""
    raw = (raw_json or "").strip()
    if raw:
        text = raw
        if not raw.startswith("{"):
            try:
                text = base64.b64decode(raw + "=" * (-len(raw) % 4), validate=False).decode("utf-8")
            except (binascii.Error, UnicodeDecodeError) as exc:
                raise CredentialError("PUSH_CREDENTIAL_JSON_INVALID", "EDUSYNC_FCM_SERVICE_ACCOUNT_JSON n’est ni du JSON ni du JSON en base64") from exc
        try:
            info = json.loads(text)
        except json.JSONDecodeError as exc:
            raise CredentialError("PUSH_CREDENTIAL_JSON_INVALID", "EDUSYNC_FCM_SERVICE_ACCOUNT_JSON : JSON illisible (une seule ligne attendue, ou base64)") from exc
    elif (file_path or "").strip():
        path = file_path.strip()
        if not os.path.exists(path):
            raise CredentialError("PUSH_CREDENTIAL_FILE_MISSING", "EDUSYNC_FCM_SERVICE_ACCOUNT_FILE : fichier absent dans le conteneur (non monté)")
        if not os.access(path, os.R_OK):
            raise CredentialError("PUSH_CREDENTIAL_FILE_UNREADABLE", "EDUSYNC_FCM_SERVICE_ACCOUNT_FILE : fichier présent mais illisible par le processus (droits)")
        try:
            with open(path, encoding="utf-8") as fh:
                info = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise CredentialError("PUSH_CREDENTIAL_JSON_INVALID", "EDUSYNC_FCM_SERVICE_ACCOUNT_FILE : contenu JSON illisible") from exc
    else:
        raise CredentialError("PUSH_CREDENTIAL_MISSING", "Ni EDUSYNC_FCM_SERVICE_ACCOUNT_JSON ni EDUSYNC_FCM_SERVICE_ACCOUNT_FILE")
    if not isinstance(info, dict) or info.get("type") != "service_account" or any(not info.get(k) for k in REQUIRED_SA):
        raise CredentialError("PUSH_CREDENTIAL_NOT_SERVICE_ACCOUNT", "Le JSON n’est pas une clé de compte de service Firebase complète")
    return info


def _c(name: str, ok: bool | None, detail: str) -> dict:
    return {"name": name, "ok": ok, "detail": detail}


def _kind(v: str | None) -> str:
    return (v or "disabled").strip().lower()


def email_checks(cfg, role: str) -> list[dict]:
    kind = _kind(cfg.email_provider)
    out = [_c("EDUSYNC_EMAIL_PROVIDER", kind == "smtp", f"vaut « {kind} »" + ("" if kind == "smtp" else " (attendu « smtp » pour Brevo)"))]
    out.append(_c("EDUSYNC_SMTP_HOST", bool(cfg.smtp_host), cfg.smtp_host if cfg.smtp_host else "absent"))
    out.append(_c("EDUSYNC_SMTP_PORT", bool(cfg.smtp_port), str(cfg.smtp_port or "absent")))
    sec = (cfg.smtp_security or "").lower()
    out.append(_c("EDUSYNC_SMTP_SECURITY", sec in ("starttls", "tls"), sec or "absent"))
    out.append(_c("EDUSYNC_SMTP_FROM_EMAIL", bool(cfg.smtp_from_email and EMAIL_RX.match(cfg.smtp_from_email)),
                  "présente" if cfg.smtp_from_email and EMAIL_RX.match(cfg.smtp_from_email) else "absente ou invalide"))
    if role == "worker":
        out.append(_c("EDUSYNC_SMTP_USERNAME", bool(cfg.smtp_username), "présent" if cfg.smtp_username else "absent"))
        out.append(_c("EDUSYNC_SMTP_PASSWORD", bool(cfg.smtp_password), "présent (jamais affiché)" if cfg.smtp_password else "absent dans ce processus"))
    url = cfg.public_app_url or ""
    out.append(_c("EDUSYNC_PUBLIC_APP_URL", url.startswith("https://"), "HTTPS" if url.startswith("https://") else "doit commencer par https:// (liens d’invitation)"))
    return out


def push_checks(cfg, role: str) -> list[dict]:
    kind = _kind(cfg.push_provider)
    out = [_c("EDUSYNC_PUSH_PROVIDER", kind == "fcm", f"vaut « {kind} »" + ("" if kind == "fcm" else " (attendu « fcm »)"))]
    if role == "worker":
        src = "json" if (cfg.fcm_service_account_json or "").strip() else "file" if (cfg.fcm_service_account_file or "").strip() else None
        try:
            info = load_service_account(cfg.fcm_service_account_file, cfg.fcm_service_account_json)
            out.append(_c("Compte de service Firebase", True, f"lu ({'secret JSON' if src == 'json' else 'fichier monté'}), projet {info.get('project_id')}"))
        except CredentialError as exc:
            out.append(_c("Compte de service Firebase", False, f"{exc.code} : {exc.detail}"))
    else:
        web = (cfg.fcm_web_config_json or "").strip()
        try:
            conf = json.loads(web) if web else None
            ok = isinstance(conf, dict) and all(conf.get(k) for k in ("apiKey", "projectId", "appId", "messagingSenderId"))
            out.append(_c("EDUSYNC_FCM_WEB_CONFIG_JSON", ok, f"projet {conf.get('projectId')}" if ok else "absente ou incomplète (apiKey, projectId, appId, messagingSenderId)"))
        except json.JSONDecodeError:
            out.append(_c("EDUSYNC_FCM_WEB_CONFIG_JSON", False, "JSON illisible (une seule ligne attendue)"))
        vapid = (cfg.fcm_vapid_public_key or "").strip()
        out.append(_c("EDUSYNC_FCM_VAPID_PUBLIC_KEY", bool(re.fullmatch(r"[A-Za-z0-9_\-]{80,100}=?", vapid)),
                      "présente" if vapid and re.fullmatch(r"[A-Za-z0-9_\-]{80,100}=?", vapid) else "absente ou au mauvais format (clé publique Web Push)"))
    return out


def web_project_id(cfg) -> str | None:
    try:
        return (json.loads(cfg.fcm_web_config_json or "{}") or {}).get("projectId")
    except json.JSONDecodeError:
        return None


def all_checks(cfg, role: str) -> dict:
    return {"role": role, "env": cfg.env, "email": email_checks(cfg, role), "push": push_checks(cfg, role)}


def main(argv: list[str]) -> int:
    from edusync.bootstrap.settings import Settings
    role = argv[1] if len(argv) > 1 and argv[1] in ("api", "worker") else "worker"
    cfg = Settings()
    report = all_checks(cfg, role)
    if role == "worker":
        import asyncio
        from edusync.shared.messaging.health import check_all
        snap = asyncio.run(check_all(cfg))
        report["health"] = {k: {x: v.get(x) for x in ("provider", "ok", "latency_ms", "error_code", "project_id")} for k, v in snap["channels"].items()}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
