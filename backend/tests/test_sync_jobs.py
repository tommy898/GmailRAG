import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.sync_jobs import (
    ClaimedGmailSyncJob,
    EnqueuedGmailSyncJob,
    GmailAccountNotConnectedError,
    SyncJobStateError,
    claim_next_gmail_sync_job,
    complete_gmail_sync_job,
    enqueue_gmail_sync_job,
    fail_gmail_sync_job,
)


class GmailSyncJobPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.profile_id = uuid.uuid4()
        self.gmail_account_id = uuid.uuid4()
        self.job_id = uuid.uuid4()
        self.connection_context = MagicMock()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection_context.__enter__.return_value = self.connection
        self.connection.cursor.return_value.__enter__.return_value = self.cursor

    @patch("app.sync_jobs.get_connection")
    def test_creates_pending_job_for_authenticated_profiles_account(
        self,
        get_connection,
    ):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.side_effect = [
            (self.gmail_account_id,),
            None,
            (self.job_id, "pending"),
        ]

        result = enqueue_gmail_sync_job(self.profile_id)

        self.assertEqual(
            result,
            EnqueuedGmailSyncJob(
                job_id=self.job_id,
                status="pending",
                created=True,
            ),
        )
        account_sql, account_parameters = self.cursor.execute.call_args_list[
            0
        ].args
        normalized_account_sql = " ".join(account_sql.split())
        self.assertIn("where ga.profile_id = %s", normalized_account_sql)
        self.assertIn("for update of ga", normalized_account_sql)
        self.assertIn(
            "ga.access_token_encrypted is not null",
            normalized_account_sql,
        )
        self.assertIn(
            "ga.refresh_token_encrypted is not null",
            normalized_account_sql,
        )
        self.assertEqual(account_parameters, (self.profile_id,))

        insert_sql, insert_parameters = self.cursor.execute.call_args_list[
            2
        ].args
        normalized_insert_sql = " ".join(insert_sql.split())
        self.assertIn("insert into sync_jobs", normalized_insert_sql)
        self.assertIn("'gmail_sync'", normalized_insert_sql)
        self.assertIn("'pending'", normalized_insert_sql)
        self.assertEqual(insert_parameters, (self.gmail_account_id,))

    @patch("app.sync_jobs.get_connection")
    def test_reuses_existing_active_job(self, get_connection):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.side_effect = [
            (self.gmail_account_id,),
            (self.job_id, "running"),
        ]

        result = enqueue_gmail_sync_job(self.profile_id)

        self.assertEqual(
            result,
            EnqueuedGmailSyncJob(
                job_id=self.job_id,
                status="running",
                created=False,
            ),
        )
        self.assertEqual(self.cursor.execute.call_count, 2)
        active_job_sql = " ".join(
            self.cursor.execute.call_args_list[1].args[0].split()
        )
        self.assertIn(
            "status in ('pending', 'running')",
            active_job_sql,
        )

    @patch("app.sync_jobs.get_connection")
    def test_rejects_profile_without_connected_gmail(self, get_connection):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = None

        with self.assertRaises(GmailAccountNotConnectedError):
            enqueue_gmail_sync_job(self.profile_id)

        self.assertEqual(self.cursor.execute.call_count, 1)


class GmailSyncJobLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.job_id = uuid.uuid4()
        self.gmail_account_id = uuid.uuid4()
        self.connection_context = MagicMock()
        self.connection = MagicMock()
        self.cursor = MagicMock()
        self.connection_context.__enter__.return_value = self.connection
        self.connection.cursor.return_value.__enter__.return_value = self.cursor

    @patch("app.sync_jobs.get_connection")
    def test_claim_returns_none_when_queue_is_empty(self, get_connection):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = None

        self.assertIsNone(claim_next_gmail_sync_job())
        self.assertEqual(self.cursor.execute.call_count, 1)

    @patch("app.sync_jobs.get_connection")
    def test_claim_locks_oldest_pending_job_and_marks_account_syncing(
        self,
        get_connection,
    ):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = (
            self.job_id,
            self.gmail_account_id,
        )

        claimed = claim_next_gmail_sync_job()

        self.assertEqual(
            claimed,
            ClaimedGmailSyncJob(
                job_id=self.job_id,
                gmail_account_id=self.gmail_account_id,
            ),
        )
        claim_sql = " ".join(
            self.cursor.execute.call_args_list[0].args[0].split()
        )
        self.assertIn("status = 'pending'", claim_sql)
        self.assertIn("for update skip locked", claim_sql)
        self.assertIn("status = 'running'", claim_sql)
        account_sql, account_parameters = self.cursor.execute.call_args_list[
            1
        ].args
        self.assertIn("sync_status = 'syncing'", " ".join(account_sql.split()))
        self.assertEqual(account_parameters, (self.gmail_account_id,))

    @patch("app.sync_jobs.get_connection")
    def test_completion_marks_job_done_and_account_ready(self, get_connection):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = (self.job_id,)

        complete_gmail_sync_job(self.job_id, self.gmail_account_id)

        job_sql, job_parameters = self.cursor.execute.call_args_list[0].args
        normalized_job_sql = " ".join(job_sql.split())
        self.assertIn("status = 'done'", normalized_job_sql)
        self.assertIn("status = 'running'", normalized_job_sql)
        self.assertEqual(
            job_parameters,
            (self.job_id, self.gmail_account_id),
        )
        account_sql, account_parameters = self.cursor.execute.call_args_list[
            1
        ].args
        normalized_account_sql = " ".join(account_sql.split())
        self.assertIn("sync_status = 'ready'", normalized_account_sql)
        self.assertIn("last_synced_at = now()", normalized_account_sql)
        self.assertEqual(account_parameters, (self.gmail_account_id,))

    @patch("app.sync_jobs.get_connection")
    def test_failure_stores_bounded_error_and_marks_account_failed(
        self,
        get_connection,
    ):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = (self.job_id,)
        long_error = "x" * 600

        fail_gmail_sync_job(
            self.job_id,
            self.gmail_account_id,
            long_error,
        )

        job_sql, job_parameters = self.cursor.execute.call_args_list[0].args
        normalized_job_sql = " ".join(job_sql.split())
        self.assertIn("status = 'failed'", normalized_job_sql)
        self.assertEqual(job_parameters[0], "Gmail sync failed")
        self.assertEqual(
            job_parameters[1:],
            (self.job_id, self.gmail_account_id),
        )
        account_sql = " ".join(
            self.cursor.execute.call_args_list[1].args[0].split()
        )
        self.assertIn("sync_status = 'failed'", account_sql)

    @patch("app.sync_jobs.get_connection")
    def test_invalid_completion_does_not_update_account(self, get_connection):
        get_connection.return_value = self.connection_context
        self.cursor.fetchone.return_value = None

        with self.assertRaises(SyncJobStateError):
            complete_gmail_sync_job(self.job_id, self.gmail_account_id)

        self.assertEqual(self.cursor.execute.call_count, 1)


if __name__ == "__main__":
    unittest.main()
