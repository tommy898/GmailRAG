import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from app.sync_jobs import GmailSyncStatus, get_gmail_sync_status


class GmailSyncStatusPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.profile_id = uuid.uuid4()
        self.connection_context = MagicMock()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection_context.__enter__.return_value = self.connection
        self.connection.cursor.return_value.__enter__.return_value = self.cursor

    @patch("app.sync_jobs.get_connection")
    def test_returns_disconnected_status_without_account(self, get_connection):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = None

        status = get_gmail_sync_status(self.profile_id)

        self.assertEqual(
            status,
            GmailSyncStatus(
                connected=False,
                sync_status=None,
                last_synced_at=None,
                job_id=None,
                job_status=None,
                job_started_at=None,
                job_finished_at=None,
                job_error_message=None,
                job_created_at=None,
            ),
        )

    @patch("app.sync_jobs.get_connection")
    def test_status_query_is_profile_isolated(self, get_connection):
        get_connection.return_value = self.connection_context
        job_id = uuid.uuid4()
        created_at = datetime(2026, 9, 27, tzinfo=UTC)
        self.cursor.fetchone.return_value = (
            True,
            "syncing",
            None,
            job_id,
            "running",
            created_at,
            None,
            None,
            created_at,
        )

        status = get_gmail_sync_status(self.profile_id)

        self.assertTrue(status.connected)
        self.assertEqual(status.job_id, job_id)
        self.assertEqual(status.job_status, "running")
        query, parameters = self.cursor.execute.call_args.args
        normalized_query = " ".join(query.split())
        self.assertIn("where ga.profile_id = %s", normalized_query)
        self.assertIn("gmail_account_id = ga.id", normalized_query)
        self.assertEqual(parameters, (self.profile_id,))

    @patch("app.sync_jobs.get_connection")
    def test_unknown_database_error_is_not_exposed(self, get_connection):
        get_connection.return_value = self.connection_context
        created_at = datetime(2026, 9, 27, tzinfo=UTC)
        self.cursor.fetchone.return_value = (
            True,
            "failed",
            None,
            uuid.uuid4(),
            "failed",
            created_at,
            created_at,
            "provider response containing secret-token",
            created_at,
        )

        status = get_gmail_sync_status(self.profile_id)

        self.assertEqual(status.job_error_message, "Gmail sync failed")


if __name__ == "__main__":
    unittest.main()
