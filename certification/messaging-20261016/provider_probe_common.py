"""Shared helpers of the REAL provider probes (email_provider_probe, sms_provider_probe, push_provider_probe).

They call the production adapters directly with the configured secrets (environment / secret store, never printed)
and a test recipient given by the operator. Without secrets or recipient they record EXTERNAL_REQUIRED — never PASS.
A provider acceptance (SENT) is recorded as REAL_ACCEPTED; reception on the real device / inbox is confirmed by a
human and written down in EXTERNAL_MESSAGING_CERTIFICATION.md. A fake provider is refused here.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend" / "src"))

from edusync.bootstrap.settings import Settings  # noqa: E402


def settings() -> Settings:
    return Settings()


def finish(name: str, status: str, checks: list[dict], **extra) -> None:
    """status: EXTERNAL_REQUIRED | REAL_ACCEPTED | REAL_FAILED."""
    out = Path(__file__).with_name(f"{name}-live.json")
    out.write_text(json.dumps({"probe": name, "status": status, "at": datetime.now(timezone.utc).isoformat(), "checks": checks, **extra},
                              indent=1, ensure_ascii=False), encoding="utf-8")
    for c in checks:
        print(f"{c['result']} {c['check']}" + (f" — {c['detail']}" if c.get("detail") else ""))
    print(f"== {status} -> {out.name}")
    sys.exit(1 if status == "REAL_FAILED" else 0)


def check(checks: list[dict], name: str, result: str, detail: str = "") -> None:
    checks.append({"check": name, "result": result, "detail": str(detail)[:300]})
