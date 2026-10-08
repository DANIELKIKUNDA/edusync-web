"""EduSync — local backup and verified restore exercise (hardening G, 2026-10).

    python tools/local/backup_restore.py [--db edusync_claude_fresh]

1. Backup: pg_dump (custom format) of the database + every object the database references (generated documents,
   school logos), each with its SHA-256, into .local/backups/<db>-<timestamp>/ (private, never versioned).
2. Restore into an isolated database (<db>_restore_check) and an isolated object prefix (restore-check/<timestamp>/).
3. Verify: row counts of schools, users, memberships, roles, assignments, documents, audit, notifications are
   identical; every restored object has the expected SHA-256; the restored audit trail is still append-only.
4. Write .local/backups/last.json {"finished_at", "ok", "restore_verified", ...} read by the health screen.

The production database is only read; nothing is written to it. Secrets come from .local/certification.env.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
LOCAL = ROOT / ".local"
PG_BIN = Path(os.environ.get("EDUSYNC_PG_BIN", r"C:\Program Files\PostgreSQL\16\bin"))
COUNTED = ("schools", "users", "school_memberships", "rbac_roles", "rbac_role_capabilities", "rbac_assignments",
           "generated_documents", "school_branding", "audit_events", "notifications", "platform_account_status")


def load_env() -> dict[str, str]:
    env = dict(os.environ)
    for line in (LOCAL / "certification.env").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env.setdefault(k, v)
    return env


def pg_args(url: str) -> tuple[list[str], dict[str, str]]:
    u = urlparse(url.replace("postgresql+psycopg://", "postgresql://"))
    return ["-h", u.hostname or "127.0.0.1", "-p", str(u.port or 5432), "-U", unquote(u.username or "")], {"PGPASSWORD": unquote(u.password or "")}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="edusync_claude_fresh")
    a = ap.parse_args()
    env = load_env()
    owner_base = env["EDUSYNC_OWNER_DATABASE_URL"].rsplit("/", 1)[0]
    src_url, chk_db = f"{owner_base}/{a.db}", f"{a.db}_restore_check"
    sys.path.insert(0, str(ROOT / "backend" / "src"))
    os.environ.update({k: v for k, v in env.items() if k.startswith("EDUSYNC_")})
    from sqlalchemy import create_engine, text
    from edusync.bootstrap.settings import Settings
    from edusync.shared.infrastructure.object_storage import build_object_storage

    settings = Settings()
    storage = build_object_storage(settings)
    if storage is None:
        print("Stockage objet non configuré : sauvegarde impossible.")
        return 2
    started = time.time()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = LOCAL / "backups" / f"{a.db}-{stamp}"
    (out / "objects").mkdir(parents=True)
    report: dict = {"database": a.db, "started_at": datetime.now(timezone.utc).isoformat(), "checks": []}

    def check(name: str, ok: bool, detail: str = "") -> None:
        report["checks"].append({"check": name, "pass": bool(ok), "detail": detail})
        print(("PASS " if ok else "FAIL ") + name + (f" : {detail}" if detail else ""), flush=True)

    # ---------- 1. backup ----------
    src = create_engine(src_url)
    with src.connect() as c:
        counts = {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in COUNTED}  # fixed table list, no user input
        objects = [dict(r) for r in c.execute(text("""
            SELECT object_key AS key, sha256 FROM generated_documents WHERE byte_size > 0
            UNION SELECT logo_object_key, logo_sha256 FROM school_branding""")).mappings()]
    args, pgenv = pg_args(src_url)
    dump = out / "database.dump"
    t0 = time.time()
    r = subprocess.run([str(PG_BIN / "pg_dump.exe"), *args, "-Fc", "-f", str(dump), a.db], env={**os.environ, **pgenv}, capture_output=True, text=True)
    check("Sauvegarde PostgreSQL (pg_dump, format custom)", r.returncode == 0 and dump.stat().st_size > 0, f"{dump.stat().st_size // 1024} Ko en {time.time() - t0:.1f} s" if dump.exists() else r.stderr[-200:])
    manifest, missing = [], 0
    for o in objects:
        try:
            data = storage.get(o["key"])
        except Exception:  # noqa: BLE001 — reported as a missing object, the backup continues
            missing += 1
            continue
        name = sha(o["key"].encode())[:24]
        (out / "objects" / name).write_bytes(data)
        manifest.append({"key": o["key"], "file": name, "sha256": sha(data), "expected": o["sha256"].strip() if o["sha256"] else None})
    (out / "manifest.json").write_text(json.dumps({"counts": counts, "objects": manifest}, indent=2), encoding="utf-8")
    check("Sauvegarde des objets référencés", missing == 0, f"{len(manifest)} objet(s), {missing} introuvable(s)")
    mism = [m["key"] for m in manifest if m["expected"] and m["expected"] != "0" * 64 and m["expected"] != m["sha256"]]
    check("Objets sauvegardés conformes à l'empreinte enregistrée en base", not mism, f"{len(mism)} écart(s)")

    # ---------- 2. restore into isolated targets ----------
    admin = create_engine(f"{owner_base}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{chk_db}" WITH (FORCE)'))  # name derived from --db, quoted
        c.execute(text(f'CREATE DATABASE "{chk_db}"'))
    t0 = time.time()
    r = subprocess.run([str(PG_BIN / "pg_restore.exe"), *args, "-d", chk_db, "--exit-on-error", str(dump)], env={**os.environ, **pgenv}, capture_output=True, text=True)
    check("Restauration PostgreSQL dans une base isolée", r.returncode == 0, f"{time.time() - t0:.1f} s" if r.returncode == 0 else r.stderr[-300:])
    # Isolated prefix of the same bucket (local S3 credentials are scoped to the documents bucket).
    prefix = f"restore-check/{stamp}/"
    for m in manifest:
        storage.put(prefix + m["key"], (out / "objects" / m["file"]).read_bytes(), content_type="application/octet-stream")

    # ---------- 3. verify ----------
    chk = create_engine(f"{owner_base}/{chk_db}")
    with chk.connect() as c:
        restored = {t: c.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in COUNTED}
    diff = {t: (counts[t], restored[t]) for t in COUNTED if counts[t] != restored[t]}
    check("Écoles, comptes, rôles, attributions, documents, audit : comptes identiques", not diff, json.dumps(counts) if not diff else json.dumps(diff))
    bad = [m["key"] for m in manifest if sha(storage.get(prefix + m["key"])) != m["sha256"]]
    check("Objets restaurés : empreintes SHA-256 identiques", not bad, f"{len(manifest) - len(bad)}/{len(manifest)}")
    try:
        with chk.begin() as c:
            c.execute(text("UPDATE audit_events SET reason='x' WHERE id=(SELECT id FROM audit_events LIMIT 1)"))
        check("Audit restauré toujours en ajout seul", False, "modification acceptée")
    except Exception:  # noqa: BLE001
        check("Audit restauré toujours en ajout seul", True)
    with chk.connect() as c:
        rls = c.execute(text("SELECT count(*) FROM pg_class WHERE relname IN ('schools','notifications','rbac_roles') AND relrowsecurity AND relforcerowsecurity")).scalar_one()
    check("Sécurité au niveau des lignes (RLS) restaurée", rls == 3, f"{rls}/3 tables")
    chk.dispose(); src.dispose()
    with admin.connect() as c:
        c.execute(text(f'DROP DATABASE IF EXISTS "{chk_db}" WITH (FORCE)'))
    for m in manifest:
        storage.delete(prefix + m["key"])

    ok = all(x["pass"] for x in report["checks"])
    report.update(finished_at=datetime.now(timezone.utc).isoformat(), ok=ok, restore_verified=ok, duration_s=round(time.time() - started, 1),
                  backup_dir=str(out.relative_to(ROOT)), objects=len(manifest), dump_bytes=dump.stat().st_size)
    (LOCAL / "backups" / "last.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"== {sum(x['pass'] for x in report['checks'])}/{len(report['checks'])} PASS · {report['duration_s']} s · rapport : .local/backups/last.json")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
