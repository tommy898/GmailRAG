import unittest
import uuid
from unittest.mock import patch

from app.worker import GmailSyncRunResult, main, run_worker_loop


class GmailWorkerCommandTests(unittest.TestCase):
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
