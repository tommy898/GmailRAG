import unittest
import uuid
from unittest.mock import call, patch

from app.gmail_service import GmailMessageNormalizationError, GmailSyncPlan
from app.sync_jobs import ClaimedGmailSyncJob
from app.worker import (
    GmailSyncRunResult,
    ProcessedGmailMessage,
    run_next_gmail_sync_job,
)


class GmailSyncJobRunnerTests(unittest.TestCase):
    @patch("app.worker.prepare_gmail_sync")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_returns_none_without_claimed_job(
        self,
        claim_next_job,
        prepare_sync,
    ):
        claim_next_job.return_value = None

        self.assertIsNone(run_next_gmail_sync_job())
        prepare_sync.assert_not_called()

    @patch("app.worker.complete_gmail_sync_job")
    @patch("app.worker.fail_gmail_sync_job")
    @patch("app.worker.reconcile_full_gmail_sync")
    @patch("app.worker.delete_gmail_message")
    @patch("app.worker.process_gmail_message")
    @patch("app.worker.prepare_gmail_sync")
    @patch("app.worker.get_gmail_sync_checkpoint")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_processes_incremental_changes_and_advances_checkpoint(
        self,
        claim_next_job,
        get_checkpoint,
        prepare_sync,
        process_message,
        delete_message,
        reconcile_full_sync,
        fail_job,
        complete_job,
    ):
        job = ClaimedGmailSyncJob(uuid.uuid4(), uuid.uuid4())
        first_email = {"gmail_message_id": "message-1"}
        second_email = {"gmail_message_id": "message-2"}
        claim_next_job.return_value = job
        get_checkpoint.return_value = "history-100"
        prepare_sync.return_value = GmailSyncPlan(
            mode="incremental",
            messages=iter([first_email, second_email]),
            deleted_message_ids=("message-deleted",),
            next_history_id="history-200",
        )
        processing_results = iter(
            [
                ProcessedGmailMessage(uuid.uuid4(), 2),
                ProcessedGmailMessage(uuid.uuid4(), 3),
            ]
        )
        operation_order = []

        def record_process(*_arguments):
            operation_order.append("upsert")
            return next(processing_results)

        delete_message.side_effect = lambda *_arguments: (
            operation_order.append("delete")
        )
        process_message.side_effect = record_process

        result = run_next_gmail_sync_job(max_messages=25)

        self.assertEqual(
            result,
            GmailSyncRunResult(job.job_id, "done", 2, 5),
        )
        get_checkpoint.assert_called_once_with(job.gmail_account_id)
        prepare_sync.assert_called_once_with(
            job.gmail_account_id,
            "history-100",
            max_messages=25,
        )
        process_message.assert_has_calls(
            [
                call(job.gmail_account_id, first_email),
                call(job.gmail_account_id, second_email),
            ]
        )
        delete_message.assert_called_once_with(
            job.gmail_account_id,
            "message-deleted",
        )
        self.assertEqual(operation_order, ["delete", "upsert", "upsert"])
        reconcile_full_sync.assert_not_called()
        complete_job.assert_called_once_with(
            job.job_id,
            job.gmail_account_id,
            "history-200",
        )
        fail_job.assert_not_called()

    @patch("app.worker.complete_gmail_sync_job")
    @patch("app.worker.fail_gmail_sync_job")
    @patch("app.worker.reconcile_full_gmail_sync")
    @patch("app.worker.process_gmail_message")
    @patch("app.worker.prepare_gmail_sync")
    @patch("app.worker.get_gmail_sync_checkpoint")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_full_sync_reconciles_stale_database_messages(
        self,
        claim_next_job,
        get_checkpoint,
        prepare_sync,
        process_message,
        reconcile_full_sync,
        fail_job,
        complete_job,
    ):
        job = ClaimedGmailSyncJob(uuid.uuid4(), uuid.uuid4())
        email = {"gmail_message_id": "message-current"}
        claim_next_job.return_value = job
        get_checkpoint.return_value = None
        prepare_sync.return_value = GmailSyncPlan(
            mode="full",
            messages=iter([email]),
            deleted_message_ids=(),
            next_history_id="history-300",
        )
        process_message.return_value = ProcessedGmailMessage(
            uuid.uuid4(),
            4,
        )

        result = run_next_gmail_sync_job()

        self.assertEqual(
            result,
            GmailSyncRunResult(job.job_id, "done", 1, 4),
        )
        reconcile_full_sync.assert_called_once_with(
            job.gmail_account_id,
            ["message-current"],
        )
        complete_job.assert_called_once_with(
            job.job_id,
            job.gmail_account_id,
            "history-300",
        )
        fail_job.assert_not_called()

    @patch("app.worker.complete_gmail_sync_job")
    @patch("app.worker.fail_gmail_sync_job")
    @patch("app.worker.reconcile_full_gmail_sync")
    @patch("app.worker.delete_gmail_message")
    @patch("app.worker.process_gmail_message")
    @patch("app.worker.prepare_gmail_sync")
    @patch("app.worker.get_gmail_sync_checkpoint")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_empty_incremental_sync_still_advances_checkpoint(
        self,
        claim_next_job,
        get_checkpoint,
        prepare_sync,
        process_message,
        delete_message,
        reconcile_full_sync,
        fail_job,
        complete_job,
    ):
        job = ClaimedGmailSyncJob(uuid.uuid4(), uuid.uuid4())
        claim_next_job.return_value = job
        get_checkpoint.return_value = "history-200"
        prepare_sync.return_value = GmailSyncPlan(
            mode="incremental",
            messages=iter([]),
            deleted_message_ids=(),
            next_history_id="history-201",
        )

        result = run_next_gmail_sync_job()

        self.assertEqual(
            result,
            GmailSyncRunResult(job.job_id, "done", 0, 0),
        )
        process_message.assert_not_called()
        delete_message.assert_not_called()
        reconcile_full_sync.assert_not_called()
        fail_job.assert_not_called()
        complete_job.assert_called_once_with(
            job.job_id,
            job.gmail_account_id,
            "history-201",
        )

    @patch("app.worker.complete_gmail_sync_job")
    @patch("app.worker.fail_gmail_sync_job")
    @patch("app.worker.process_gmail_message")
    @patch("app.worker.prepare_gmail_sync")
    @patch("app.worker.get_gmail_sync_checkpoint")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_malformed_later_message_preserves_checkpoint_for_safe_retry(
        self,
        claim_next_job,
        get_checkpoint,
        prepare_sync,
        process_message,
        fail_job,
        complete_job,
    ):
        job = ClaimedGmailSyncJob(uuid.uuid4(), uuid.uuid4())
        first_email = {"gmail_message_id": "message-1"}
        malformed_email = {"gmail_message_id": "message-2"}
        claim_next_job.return_value = job
        get_checkpoint.return_value = "history-100"
        prepare_sync.return_value = GmailSyncPlan(
            mode="incremental",
            messages=iter([first_email, malformed_email]),
            deleted_message_ids=(),
            next_history_id="history-200",
        )
        process_message.side_effect = [
            ProcessedGmailMessage(uuid.uuid4(), 2),
            GmailMessageNormalizationError("private malformed payload"),
        ]

        with self.assertLogs("app.worker", level="ERROR") as captured_logs:
            result = run_next_gmail_sync_job()

        self.assertEqual(
            result,
            GmailSyncRunResult(job.job_id, "failed", 1, 2),
        )
        fail_job.assert_called_once_with(
            job.job_id,
            job.gmail_account_id,
            "A Gmail message could not be normalized",
        )
        complete_job.assert_not_called()
        self.assertNotIn(
            "private malformed payload",
            " ".join(captured_logs.output),
        )

    @patch("app.worker.complete_gmail_sync_job")
    @patch("app.worker.fail_gmail_sync_job")
    @patch("app.worker.process_gmail_message")
    @patch("app.worker.prepare_gmail_sync")
    @patch("app.worker.get_gmail_sync_checkpoint")
    @patch("app.worker.claim_next_gmail_sync_job")
    def test_failure_is_sanitized_and_does_not_advance_checkpoint(
        self,
        claim_next_job,
        get_checkpoint,
        prepare_sync,
        process_message,
        fail_job,
        complete_job,
    ):
        job = ClaimedGmailSyncJob(uuid.uuid4(), uuid.uuid4())
        email = {"gmail_message_id": "message-1"}
        claim_next_job.return_value = job
        get_checkpoint.return_value = "history-100"
        prepare_sync.return_value = GmailSyncPlan(
            mode="incremental",
            messages=iter([email]),
            deleted_message_ids=(),
            next_history_id="history-200",
        )
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
