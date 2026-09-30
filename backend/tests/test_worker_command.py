import unittest
import os
from contextlib import redirect_stderr
from io import StringIO
import uuid
from unittest.mock import patch

from app.worker import GmailSyncRunResult, main, run_worker_loop
from test_production_config import production_environment


class GmailWorkerCommandTests(unittest.TestCase):
    @patch("app.worker.load_dotenv")
    @patch("app.worker.run_next_gmail_sync_job")
    def test_targeted_execution_exits_and_never_polls(self, run_job, load_environment):
        job_id = uuid.uuid4()
        for result, expected in ((None, 0), (GmailSyncRunResult(job_id, "done", 2, 3), 0),
                                 (GmailSyncRunResult(job_id, "failed", 0, 0), 1)):
            run_job.return_value = result
            with patch.dict(os.environ, {}, clear=True), patch("app.worker.run_worker_loop") as loop:
                self.assertEqual(main(["--job-id", str(job_id)]), expected)
            run_job.assert_called_with(job_id=job_id)
            loop.assert_not_called()

    @patch("app.worker.load_dotenv")
    @patch("app.worker.run_next_gmail_sync_job")
    def test_claim_or_completion_errors_do_not_log_raw_secrets(self, run_job, load_environment):
        run_job.side_effect = RuntimeError("private-db-url-and-token")
        with patch.dict(os.environ, {}, clear=True), self.assertLogs("app.worker", level="ERROR") as logs:
            self.assertEqual(main(["--job-id", str(uuid.uuid4())]), 1)
        self.assertNotIn("private-db-url-and-token", "".join(logs.output))

    @patch("app.worker.load_dotenv")
    @patch("app.worker.run_next_gmail_sync_job")
    @patch("app.worker.run_worker_loop")
    def test_production_requires_job_target_not_polling_or_once(self, loop, run_job, load_environment):
        with patch.dict(os.environ, production_environment(), clear=True):
            for args in ([], ["--once"]):
                with self.assertLogs("app.worker", level="ERROR"):
                    self.assertEqual(main(args), 1)
            run_job.return_value = None
            self.assertEqual(main(["--job-id", str(uuid.uuid4())]), 0)
        loop.assert_not_called()
        self.assertEqual(run_job.call_count, 1)

    @patch("app.worker.load_dotenv")
    @patch("app.worker.recover_interrupted_gmail_sync_job")
    @patch("app.worker.run_next_gmail_sync_job")
    def test_operator_recovery_requires_confirmation_and_never_processes(self, run_job, recover, load_environment):
        job_id = uuid.uuid4()
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit) as caught:
            main(["--recover-job", str(job_id)])
        self.assertEqual(caught.exception.code, 2)
        recover.assert_not_called()
        load_environment.assert_not_called()
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(main(["--recover-job", str(job_id), "--confirm-worker-stopped"]), 0)
        recover.assert_called_once_with(job_id)
        run_job.assert_not_called()

    def test_invalid_uuid_and_conflicting_modes_stop_before_work(self):
        for args in (["--job-id", "bad"], ["--job-id", str(uuid.uuid4()), "--once"],
                     ["--confirm-worker-stopped"]):
            with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
                main(args)

    @patch("app.worker.load_dotenv")
    @patch("app.worker.run_next_gmail_sync_job")
    def test_once_exits_successfully_when_queue_is_empty(
        self,
        run_next_job,
        load_dotenv,
    ):
        run_next_job.return_value = None

        self.assertEqual(main(["--once"]), 0)
        run_next_job.assert_called_once_with()
        load_dotenv.assert_called_once_with()

    @patch("app.worker.load_dotenv")
    @patch("app.worker.run_next_gmail_sync_job")
    def test_once_returns_failure_for_failed_job(
        self,
        run_next_job,
        load_dotenv,
    ):
        run_next_job.return_value = GmailSyncRunResult(
            job_id=uuid.uuid4(),
            status="failed",
            messages_processed=0,
            chunks_indexed=0,
        )

        self.assertEqual(main(["--once"]), 1)
        load_dotenv.assert_called_once_with()

    @patch("app.worker.time.sleep")
    @patch("app.worker.run_next_gmail_sync_job")
    def test_loop_waits_when_queue_is_empty(self, run_next_job, sleep):
        run_next_job.return_value = None
        sleep.side_effect = KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            run_worker_loop(2.5)

        sleep.assert_called_once_with(2.5)


if __name__ == "__main__":
    unittest.main()
