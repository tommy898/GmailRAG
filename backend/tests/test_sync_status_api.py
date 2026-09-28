import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.auth import InvalidAccessTokenError
from app.main import app
from app.sync_jobs import GmailSyncStatus


class GmailSyncStatusRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.profile_id = uuid.uuid4()
        self.authorization_header = {"Authorization": "Bearer test-token"}

    @patch("app.main.get_gmail_sync_status")
    def test_missing_authentication_stops_before_status_query(self, get_status):
        response = self.client.get("/sync/status")

        self.assertEqual(response.status_code, 401)
        get_status.assert_not_called()

    @patch("app.main.get_gmail_sync_status")
    @patch("app.auth.verify_supabase_access_token")
    def test_invalid_authentication_stops_before_status_query(
        self,
        verify_token,
        get_status,
    ):
        verify_token.side_effect = InvalidAccessTokenError

        response = self.client.get(
            "/sync/status",
            headers=self.authorization_header,
        )

        self.assertEqual(response.status_code, 401)
        get_status.assert_not_called()

    @patch("app.main.get_gmail_sync_status")
    @patch("app.auth.verify_supabase_access_token")
    def test_returns_only_safe_profile_status(self, verify_token, get_status):
        verify_token.return_value = self.profile_id
        job_id = uuid.uuid4()
        created_at = datetime(2026, 9, 27, tzinfo=UTC)
        get_status.return_value = GmailSyncStatus(
            connected=True,
            sync_status="failed",
            last_synced_at=None,
            job_id=job_id,
            job_status="failed",
            job_started_at=created_at,
            job_finished_at=created_at,
            job_error_message="Gmail messages could not be indexed",
            job_created_at=created_at,
        )

        response = self.client.get(
            "/sync/status",
            headers=self.authorization_header,
        )

        self.assertEqual(response.status_code, 200)
        get_status.assert_called_once_with(self.profile_id)
        self.assertEqual(response.json()["job"]["job_id"], str(job_id))
        self.assertEqual(response.json()["job"]["status"], "failed")
        self.assertNotIn("gmail_account_id", response.text)
        self.assertNotIn("access_token", response.text)
        self.assertNotIn("refresh_token", response.text)


if __name__ == "__main__":
    unittest.main()
