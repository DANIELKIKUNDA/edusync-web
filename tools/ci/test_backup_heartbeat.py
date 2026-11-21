"""Non-regression: R2 failures must trigger Healthchecks /fail, not a false OK.

Runs the real backup.sh in one-shot mode with fake PostgreSQL, rclone and curl
executables. All data/status paths are redirected to an isolated temp directory.
There are no network requests and no production resources are touched.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "deploy" / "backup" / "backup.sh"


class BackupHeartbeatTests(unittest.TestCase):
    def run_backup(self, *, offsite: bool, r2_fails: bool = False, restore_fails: bool = False):
        with tempfile.TemporaryDirectory() as workdir:
            temp = Path(workdir)
            (temp / "backups").mkdir()
            (temp / "status").mkdir()
            fake_bin = temp / "fake-bin"
            fake_bin.mkdir()

            source = SCRIPT.read_text(encoding="utf-8")
            self.assertEqual(source.count("OUT=/backups\n"), 1)
            self.assertEqual(source.count("STATUS=/backup-status/last.json\n"), 1)
            source = source.replace("OUT=/backups\n", f'OUT="{temp / "backups"}"\n')
            source = source.replace(
                "STATUS=/backup-status/last.json\n",
                f'STATUS="{temp / "status" / "last.json"}"\n',
            )
            script = temp / "backup.sh"
            script.write_text(source, encoding="utf-8")

            programs = {
                "psql": "#!/bin/sh\nprintf '0\\n'\n",
                "pg_dump": """#!/usr/bin/env python3
import pathlib, sys
args = sys.argv[1:]
pathlib.Path(args[args.index('-f') + 1]).write_bytes(b'fake-dump')
""",
                "pg_restore": """#!/usr/bin/env python3
import os, sys
sys.exit(1 if os.getenv('MOCK_RESTORE_FAIL') == '1' else 0)
""",
                "createdb": "#!/bin/sh\nexit 0\n",
                "dropdb": "#!/bin/sh\nexit 0\n",
                "rclone": """#!/usr/bin/env python3
import os, pathlib, sys
args = sys.argv[1:]
if args[0] == 'mkdir':
    sys.exit(0)
if args[0] == 'copy':
    if args[-1].startswith('offsite:'):
        sys.exit(9 if os.getenv('MOCK_R2_FAIL') == '1' else 0)
    dest = pathlib.Path(args[-1])
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'mock-object.txt').write_text('document')
    sys.exit(0)
sys.exit(2)
""",
                "curl": """#!/usr/bin/env python3
import os, pathlib, sys
url = sys.argv[-1]
kind = 'start' if url.endswith('/start') else 'fail' if url.endswith('/fail') else 'success'
with pathlib.Path(os.environ['MOCK_PINGS']).open('a') as stream:
    stream.write(kind + '\\n')
""",
            }
            for name, body in programs.items():
                executable = fake_bin / name
                executable.write_text(body, encoding="utf-8")
                executable.chmod(0o755)

            pings = temp / "pings.txt"
            env = {
                **os.environ,
                "PATH": f"{fake_bin}{os.pathsep}{os.environ['PATH']}",
                "PGUSER": "test",
                "PGPASSWORD": "test",
                "PGDATABASE": "edusync",
                "BACKUP_SOURCE_BUCKET": "documents",
                "BACKUP_KEEP_DAYS": "7",
                "BACKUP_OFFSITE": "offsite:backup/production" if offsite else "",
                "BACKUP_HEARTBEAT_URL": "https://healthchecks.invalid/mock-check",
                "MOCK_PINGS": str(pings),
                "MOCK_R2_FAIL": "1" if r2_fails else "0",
                "MOCK_RESTORE_FAIL": "1" if restore_fails else "0",
            }
            result = subprocess.run(
                ["/bin/sh", str(script), "once"],
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
                check=False,
            )
            status = json.loads((temp / "status" / "last.json").read_text(encoding="utf-8"))
            events = pings.read_text(encoding="utf-8").splitlines()
            return result, status, events

    def test_r2_copy_failure_sends_fail_and_marks_backup_failed(self):
        result, status, events = self.run_backup(offsite=True, r2_fails=True)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((status["ok"], status["restore_verified"], status["offsite"]), (False, True, False))
        self.assertIn("copie hors site en échec", status["detail"])
        self.assertEqual(events, ["start", "fail"])

    def test_verified_r2_copy_sends_success(self):
        result, status, events = self.run_backup(offsite=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((status["ok"], status["restore_verified"], status["offsite"]), (True, True, True))
        self.assertEqual(events, ["start", "success"])

    def test_optional_offsite_unset_keeps_local_backup_behavior(self):
        result, status, events = self.run_backup(offsite=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((status["ok"], status["restore_verified"], status["offsite"]), (True, True, False))
        self.assertEqual(events, ["start", "success"])

    def test_restore_failure_sends_fail_even_when_r2_succeeds(self):
        result, status, events = self.run_backup(offsite=True, restore_fails=True)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((status["ok"], status["restore_verified"]), (False, False))
        self.assertEqual(events, ["start", "fail"])


if __name__ == "__main__":
    unittest.main()
