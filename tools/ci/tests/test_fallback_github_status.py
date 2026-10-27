"""Offline unit tests for the external GitHub commit-status publisher.

No GitHub network requests are sent: urllib.request.urlopen is mocked.
Run: python3 -m unittest discover -s tools/ci/tests -p "test_fallback_github_status.py"
"""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "tools/ci/fallback_github_status.py"
SPEC = importlib.util.spec_from_file_location("fallback_github_status", SOURCE)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
SHA = "a" * 40


class FakeResponse:
    status = 201

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class ExternalStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="edusync-gh-status-")
        self.addCleanup(self.temp.cleanup)
        self.token_path = Path(self.temp.name, "status-token")
        self.token_path.write_text("github_pat_" + ("x" * 80) + "\n", encoding="ascii")
        self.token_path.chmod(0o600)
        self.env = patch.dict(os.environ, {"EDUSYNC_GITHUB_STATUS_TOKEN_FILE": str(self.token_path)})
        self.env.start()
        self.addCleanup(self.env.stop)

    def run_main(self, *args):
        with patch.object(MODULE.sys, "argv", ["fallback_github_status.py", *args]):
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                return MODULE.main()

    def test_success_posts_exact_sha_and_separate_status_context(self):
        requests = []

        def record(req, timeout):
            requests.append((req, timeout))
            return FakeResponse()

        with patch.object(MODULE.urllib.request, "urlopen", side_effect=record):
            self.assertEqual(self.run_main(SHA, "success", "Tests CI locaux PASS"), 0)
        self.assertEqual(len(requests), 1)
        request, timeout = requests[0]
        self.assertIn(f"/statuses/{SHA}", request.full_url)
        self.assertEqual(timeout, 15)
        body = json.loads(request.data)
        self.assertEqual(body["state"], "success")
        self.assertEqual(body["context"], "external/edusync-ci")
        self.assertNotIn("target_url", body)

    def test_rejects_invalid_sha_or_status_without_network(self):
        with patch.object(MODULE.urllib.request, "urlopen") as send:
            self.assertEqual(self.run_main("abcd", "success", "nimporte"), 64)
            self.assertEqual(self.run_main(SHA, "unknown", "nimporte"), 64)
            self.assertEqual(self.run_main(SHA, "success", ""), 64)
            send.assert_not_called()

    def test_rejects_token_readable_by_other_users(self):
        self.token_path.chmod(0o644)
        with patch.object(MODULE.urllib.request, "urlopen") as send:
            self.assertEqual(self.run_main(SHA, "pending", "Tests en cours"), 74)
            send.assert_not_called()

    def test_network_failure_never_claims_success(self):
        from urllib.error import URLError
        with patch.object(MODULE.urllib.request, "urlopen", side_effect=URLError("offline")):
            self.assertEqual(self.run_main(SHA, "success", "Tests CI locaux PASS"), 74)


if __name__ == "__main__":
    unittest.main()
