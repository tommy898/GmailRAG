import unittest
import uuid
from unittest.mock import call, patch

from app.sync_jobs import ClaimedGmailSyncJob
from app.worker import (
    GmailSyncRunResult,
    ProcessedGmailMessage,
    run_next_gmail_sync_job,
)


class GmailSyncJobRunnerTests(unittest.TestCase):
    @patch("app.worker.iter_normalized_gmail_messages")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_returns_none_without_claimed_job(
        self,
        claim_next_job,
        iter_messages,
    ):
        claim_next_job.return_value = None

        self.assertIsNone(run_next_gmail_sync_job())
        iter_messages.assert_not_called()

    @patch("app.worker.complete_gmail_sync_job")
    @patch("app.worker.fail_gmail_sync_job")
    @patch("app.worker.process_gmail_message")
    @patch("app.worker.iter_normalized_gmail_messages")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_processes_stream_and_completes_job(
        self,
        claim_next_job,
        iter_messages,
        process_message,
        fail_job,
        complete_job,
    ):
        job = ClaimedGmailSyncJob(uuid.uuid4(), uuid.uuid4())
        first_email = {"gmail_message_id": "message-1"}
        second_email = {"gmail_message_id": "message-2"}
        claim_next_job.return_value = job
        iter_messages.return_value = iter([first_email, second_email])
        process_message.side_effect = [
            ProcessedGmailMessage(uuid.uuid4(), 2),
            ProcessedGmailMessage(uuid.uuid4(), 3),
        ]

        result = run_next_gmail_sync_job(max_messages=25)

        self.assertEqual(
            result,
            GmailSyncRunResult(job.job_id, "done", 2, 5),
        )
        iter_messages.assert_called_once_with(
            job.gmail_account_id,
            max_messages=25,
        )
        process_message.assert_has_calls(
            [
                call(job.gmail_account_id, first_email),
                call(job.gmail_account_id, second_email),
            ]
        )
        complete_job.assert_called_once_with(
            job.job_id,
            job.gmail_account_id,
        )
        fail_job.assert_not_called()

    @patch("app.worker.complete_gmail_sync_job")
    @patch("app.worker.fail_gmail_sync_job")
    @patch("app.worker.process_gmail_message")
    @patch("app.worker.iter_normalized_gmail_messages")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_failure_is_sanitized_and_marks_job_failed(
        self,
        claim_next_job,
        iter_messages,
        process_message,
        fail_job,
        complete_job,
    ):
        job = ClaimedGmailSyncJob(uuid.uuid4(), uuid.uuid4())
        email = {"gmail_message_id": "message-1"}
        claim_next_job.return_value = job
        iter_messages.return_value = iter([email])
        process_message.side_effect = RuntimeError(
            "secret-token provider response"
        )

        with self.assertLogs("app.worker", level="ERROR") as captured_logs:
            result = run_next_gmail_sync_job()

        self.assertEqual(
            result,
            GmailSyncRunResult(job.job_id, "failed", 0, 0),
        )
        fail_job.assert_called_once_with(
            job.job_id,
            job.gmail_account_id,
            "Gmail messages could not be indexed",
        )
        complete_job.assert_not_called()
        combined_logs = " ".join(captured_logs.output)
        self.assertNotIn("secret-token", combined_logs)
        self.assertNotIn("provider response", combined_logs)


if __name__ == "__main__":
    unittest.main()
