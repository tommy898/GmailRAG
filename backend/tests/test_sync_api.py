import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import InvalidAccessTokenError
from app.main import app
from app.job_dispatch import SyncJobLaunchError
from app.sync_jobs import (
    EnqueuedGmailSyncJob,
    GmailAccountNotConnectedError,
)


class GmailSyncRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.profile_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        self.authorization_header = {"Authorization": "Bearer test-token"}
        launcher = patch("app.main.launch_gmail_sync_job")
        self.launch = launcher.start()
        self.addCleanup(launcher.stop)

    @patch("app.main.enqueue_gmail_sync_job")
    def test_missing_authentication_stops_before_job_creation(self, enqueue):
        response = self.client.post("/gmail/sync")

        self.assertEqual(response.status_code, 401)
        enqueue.assert_not_called()
        self.launch.assert_not_called()

    @patch("app.main.enqueue_gmail_sync_job")
    @patch("app.auth.verify_supabase_access_token")
    def test_invalid_authentication_stops_before_job_creation(
        self,
        verify_token,
        enqueue,
    ):
        verify_token.side_effect = InvalidAccessTokenError

        response = self.client.post(
            "/gmail/sync",
            headers=self.authorization_header,
        )

        self.assertEqual(response.status_code, 401)
        enqueue.assert_not_called()
        self.launch.assert_not_called()

    @patch("app.main.enqueue_gmail_sync_job")
    @patch("app.auth.verify_supabase_access_token")
    def test_authenticated_profile_can_enqueue_sync(
        self,
        verify_token,
        enqueue,
    ):
        verify_token.return_value = self.profile_id
        enqueue.return_value = EnqueuedGmailSyncJob(
            job_id=self.job_id,
            status="pending",
            created=True,
        )

        response = self.client.post(
            "/gmail/sync",
            headers=self.authorization_header,
        )

        self.assertEqual(response.status_code, 202)
        enqueue.assert_called_once_with(self.profile_id)
        self.launch.assert_called_once_with(self.job_id)
        self.assertEqual(
            response.json(),
            {
                "job_id": str(self.job_id),
                "status": "pending",
                "created": True,
            },
        )
        self.assertNotIn("gmail_account_id", response.text)
        self.assertNotIn("token", response.text)

    @patch("app.main.enqueue_gmail_sync_job")
    @patch("app.auth.verify_supabase_access_token")
    def test_unconnected_profile_receives_sanitized_conflict(
        self,
        verify_token,
        enqueue,
    ):
        verify_token.return_value = self.profile_id
        enqueue.side_effect = GmailAccountNotConnectedError

        response = self.client.post(
            "/gmail/sync",
            headers=self.authorization_header,
        )

        self.assertEqual(response.status_code, 409)
        self.launch.assert_not_called()
        self.assertEqual(
            response.json(),
            {"detail": "Connect Gmail before starting a sync"},
        )

    @patch("app.main.enqueue_gmail_sync_job")
    @patch("app.auth.verify_supabase_access_token")
    def test_reused_pending_job_is_dispatched_again(self, verify, enqueue):
        verify.return_value = self.profile_id
        enqueue.return_value = EnqueuedGmailSyncJob(self.job_id, "pending", False)
        response = self.client.post("/gmail/sync", headers=self.authorization_header)
        self.assertEqual(response.status_code, 202)
        self.assertFalse(response.json()["created"])
        self.launch.assert_called_once_with(self.job_id)

    @patch("app.main.enqueue_gmail_sync_job")
    @patch("app.auth.verify_supabase_access_token")
    def test_reused_running_job_does_not_launch_another_execution(self, verify, enqueue):
        verify.return_value = self.profile_id
        enqueue.return_value = EnqueuedGmailSyncJob(self.job_id, "running", False)
        response = self.client.post("/gmail/sync", headers=self.authorization_header)
        self.assertEqual(response.status_code, 202)
        self.launch.assert_not_called()

    @patch("app.main.enqueue_gmail_sync_job")
    @patch("app.auth.verify_supabase_access_token")
    def test_launch_failure_is_sanitized_and_retry_uses_same_pending_job(self, verify, enqueue):
        verify.return_value = self.profile_id
        enqueue.side_effect = [EnqueuedGmailSyncJob(self.job_id, "pending", True),
                               EnqueuedGmailSyncJob(self.job_id, "pending", False)]
        self.launch.side_effect = [SyncJobLaunchError("private-provider-token"), None]
        with self.assertLogs("app.main", level="WARNING") as logs:
            first = self.client.post("/gmail/sync", headers=self.authorization_header)
        self.assertEqual(first.status_code, 503)
        self.assertNotIn("private-provider-token", first.text + "".join(logs.output))
        second = self.client.post("/gmail/sync", headers=self.authorization_header)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(second.json()["job_id"], str(self.job_id))
        self.assertEqual(self.launch.call_args_list[0], self.launch.call_args_list[1])

    @patch("app.main.enqueue_gmail_sync_job")
    @patch("app.auth.verify_supabase_access_token")
    def test_client_cannot_supply_someone_elses_job_id(self, verify, enqueue):
        verify.return_value = self.profile_id
        enqueue.return_value = EnqueuedGmailSyncJob(self.job_id, "pending", True)
        response = self.client.post("/gmail/sync", headers=self.authorization_header,
                                    json={"job_id": str(uuid.uuid4()), "profile_id": str(uuid.uuid4())})
        self.assertEqual(response.status_code, 202)
        enqueue.assert_called_once_with(self.profile_id)
        self.launch.assert_called_once_with(self.job_id)


if __name__ == "__main__":
    unittest.main()
