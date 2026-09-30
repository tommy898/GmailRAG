import os
import traceback
import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.config import ConfigurationError, get_cloud_run_job_name, get_sync_dispatch_mode
from app.job_dispatch import SyncJobLaunchError, launch_gmail_sync_job


CLOUD_ENV = {
    "APP_ENV": "development", "GMAIL_SYNC_DISPATCH": "cloud_run",
    "CLOUD_RUN_PROJECT": "gmailrag-501319", "CLOUD_RUN_REGION": "us-west1",
    "GMAIL_SYNC_JOB_NAME": "gmailrag-sync",
}


class JobDispatchTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, CLOUD_ENV, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)
        default_patcher = patch("app.job_dispatch.google.auth.default")
        session_patcher = patch("app.job_dispatch.AuthorizedSession")
        self.default = default_patcher.start()
        self.session_class = session_patcher.start()
        self.addCleanup(default_patcher.stop)
        self.addCleanup(session_patcher.stop)
        self.credentials = MagicMock()
        self.default.return_value = (self.credentials, "unused-project")
        self.session = self.session_class.return_value.__enter__.return_value
        self.response = self.session.post.return_value
        self.response.status_code = 200
        self.response.json.return_value = {"name": "projects/example/locations/us-west1/operations/op"}
        self.job_id = uuid.uuid4()

    def test_launches_one_targeted_task_without_waiting_for_execution(self):
        launch_gmail_sync_job(self.job_id)
        self.default.assert_called_once_with(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        self.session_class.assert_called_once_with(self.credentials, max_refresh_attempts=0, refresh_timeout=10)
        self.session.post.assert_called_once_with(
            "https://run.googleapis.com/v2/projects/gmailrag-501319/locations/us-west1/jobs/gmailrag-sync:run",
            json={"overrides": {"containerOverrides": [{"args": ["--job-id", str(self.job_id)]}], "taskCount": 1}},
            timeout=(5, 20), max_allowed_time=30, allow_redirects=False,
        )
        self.session.get.assert_not_called()
        self.session_class.return_value.__exit__.assert_called_once()

    def test_local_mode_never_uses_google_credentials_or_network(self):
        with patch.dict(os.environ, {"GMAIL_SYNC_DISPATCH": "local"}):
            launch_gmail_sync_job(self.job_id)
        self.default.assert_not_called()
        self.session_class.assert_not_called()

    def test_errors_and_tracebacks_never_expose_provider_bodies_or_tokens(self):
        for failure in (TimeoutError("secret-token"), RuntimeError("private-client-key")):
            self.session.post.side_effect = failure
            with self.assertRaises(SyncJobLaunchError) as caught:
                launch_gmail_sync_job(self.job_id)
            rendered = "".join(traceback.format_exception(caught.exception))
            self.assertNotIn(str(failure), rendered)
        self.assertEqual(self.session.post.call_count, 2)  # one attempt per invocation

    def test_denied_and_invalid_operation_responses_fail_closed(self):
        cases = [(403, {"error": "private-token"}), (500, {}), (200, {}),
                 (200, {"name": "op", "error": {"message": "secret"}}),
                 (200, {"name": 123}), (200, [])]
        for status, body in cases:
            self.response.status_code = status
            self.response.json.return_value = body
            with self.assertRaises(SyncJobLaunchError):
                launch_gmail_sync_job(self.job_id)
        self.response.text.__str__.assert_not_called()

    def test_adc_failure_is_sanitized(self):
        self.default.side_effect = RuntimeError("private-json-key")
        with self.assertRaisesRegex(SyncJobLaunchError, "could not be launched") as caught:
            launch_gmail_sync_job(self.job_id)
        self.assertNotIn("private-json-key", "".join(traceback.format_exception(caught.exception)))

    def test_resource_identifiers_cannot_change_endpoint_or_inject_paths(self):
        for name in ("CLOUD_RUN_PROJECT", "CLOUD_RUN_REGION", "GMAIL_SYNC_JOB_NAME"):
            for value in ("", "../other", "x?secret=token", "https://evil.example", "a/b", "has space"):
                with patch.dict(os.environ, {name: value}):
                    with self.assertRaises(ConfigurationError):
                        get_cloud_run_job_name()
        self.default.assert_not_called()

    def test_reserved_runtime_job_metadata_cannot_change_dispatch_target(self):
        with patch.dict(os.environ, {"CLOUD_RUN_JOB": "unrelated-runtime-job"}):
            self.assertEqual(
                get_cloud_run_job_name(),
                "projects/gmailrag-501319/locations/us-west1/jobs/gmailrag-sync",
            )

    def test_reserved_runtime_job_metadata_is_not_a_target_fallback(self):
        environment = CLOUD_ENV.copy()
        del environment["GMAIL_SYNC_JOB_NAME"]
        environment["CLOUD_RUN_JOB"] = "unrelated-runtime-job"
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "GMAIL_SYNC_JOB_NAME"):
                launch_gmail_sync_job(self.job_id)
        self.default.assert_not_called()
        self.session_class.assert_not_called()

    def test_production_defaults_to_hosted_and_rejects_local_or_unknown_mode(self):
        with patch.dict(os.environ, {"APP_ENV": "production"}, clear=True):
            self.assertEqual(get_sync_dispatch_mode(), "cloud_run")
            for mode in ("local", "invalid"):
                with patch.dict(os.environ, {"GMAIL_SYNC_DISPATCH": mode}):
                    with self.assertRaises(ConfigurationError):
                        get_sync_dispatch_mode()


if __name__ == "__main__":
    unittest.main()
