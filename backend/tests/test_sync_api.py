import unittest
import uuid
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import InvalidAccessTokenError
from app.main import app
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

    @patch("app.main.enqueue_gmail_sync_job")
    def test_missing_authentication_stops_before_job_creation(self, enqueue):
        response = self.client.post("/gmail/sync")

        self.assertEqual(response.status_code, 401)
        enqueue.assert_not_called()

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
        self.assertEqual(
            response.json(),
            {"detail": "Connect Gmail before starting a sync"},
        )


if __name__ == "__main__":
    unittest.main()
