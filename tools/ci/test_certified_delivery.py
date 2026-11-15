import os
import unittest
from unittest.mock import patch

import deploy_coolify as coolify
import production_release_gate as gate


class DeliveryTests(unittest.TestCase):
    def test_rejects_skipped_e2e_or_newer_failed_attempt(self):
        sha = "a" * 40

        def workflow_runs(workflow, _query):
            event = "push" if workflow == "ci.yml" else "workflow_run"
            return [{"id": workflow, "run_attempt": 1, "event": event, "head_sha": sha,
                     "head_repository": {"full_name": gate.REPO}, "conclusion": "success"}]

        def jobs(path):
            for workflow, _, name, steps in gate.EVIDENCE:
                if f"/runs/{workflow}/" in path:
                    return {"jobs": [{"name": name, "conclusion": "success", "steps": [
                        {"name": step, "conclusion": "skipped" if "Chromium" in step else "success"}
                        for step in steps]}]}
            self.fail("Workflow inattendu")

        with patch.object(gate, "runs", side_effect=workflow_runs), patch.object(gate, "gh", side_effect=jobs):
            self.assertFalse(gate.has_evidence(sha))
        with patch.object(gate, "runs", return_value=[dict(workflow_runs("ci.yml", "")[0], conclusion="failure")]):
            self.assertFalse(gate.has_evidence(sha))

    def test_owner_must_approve_the_environment(self):
        approval = {"state": "approved", "user": {"login": "DANIELKIKUNDA"}, "environments": [{"name": "production"}]}
        with patch.object(gate, "gh", return_value=[approval]):
            gate.require_owner_approval("42", "1")
            with self.assertRaises(RuntimeError):
                gate.require_owner_approval("42", "2")
        with patch.object(gate, "gh", return_value=[dict(approval, user={"login": "someone-else"})]):
            with self.assertRaises(RuntimeError):
                gate.require_owner_approval("42", "1")

    def test_coolify_applies_one_sha_and_verifies_public_health(self):
        sha = "b" * 40
        app = "application-123"
        responses = [{"build": "a" * 40}, {}, {"deployments": [{"resource_uuid": app,
                      "deployment_uuid": "deployment-123"}]}, {"status": "finished"}, {"build": sha}, {"status": "ok"}]
        config = {"COOLIFY_API_ORIGIN": "https://coolify.example", "COOLIFY_APP_UUID": app, "COOLIFY_API_TOKEN": "test"}
        with patch.dict(os.environ, config), patch.object(coolify, "call", side_effect=responses) as request:
            coolify.deploy(sha, "")
        self.assertEqual(request.call_args_list[1].args[-1], {"key": "EDUSYNC_RELEASE_SHA", "value": sha, "is_preview": False})
        self.assertEqual(request.call_args_list[-1].args, (coolify.PUBLIC_URL, "/health-api"))

    def test_rollback_with_different_migrations_stops_before_mutating_coolify(self):
        config = {"COOLIFY_API_ORIGIN": "https://coolify.example", "COOLIFY_APP_UUID": "application-123",
                  "COOLIFY_API_TOKEN": "test"}
        with patch.dict(os.environ, config), patch.object(coolify, "call", return_value={"build": "a" * 40}) as request, \
                patch.object(coolify.subprocess, "run", return_value=type("Result", (), {"returncode": 1})()):
            with self.assertRaises(RuntimeError):
                coolify.deploy("b" * 40, "a" * 40)
        request.assert_called_once_with(coolify.PUBLIC_URL, "/version.json")


if __name__ == "__main__":
    unittest.main()
