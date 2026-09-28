import unittest
import uuid
from unittest.mock import MagicMock, patch

from app.worker import ProcessedGmailMessage, process_gmail_message


class GmailMessageProcessingTests(unittest.TestCase):
    def setUp(self):
        self.gmail_account_id = uuid.uuid4()
        self.email_id = uuid.uuid4()
        self.email = {
            "gmail_message_id": "message-1",
            "body_text": "Message body",
        }

    @patch("app.worker.index_email")
    @patch("app.worker.upsert_email")
    @patch("app.worker.get_connection")
    def test_processes_one_message_in_one_connection_context(
        self,
        get_connection,
        upsert_email,
        index_email,
    ):
        connection_context = MagicMock()
        connection = MagicMock()
        get_connection.return_value = connection_context
        connection_context.__enter__.return_value = connection
        upsert_email.return_value = self.email_id
        index_email.return_value = 3

        result = process_gmail_message(
            self.gmail_account_id,
            self.email,
        )

        self.assertEqual(
            result,
            ProcessedGmailMessage(
                email_id=self.email_id,
                chunk_count=3,
            ),
        )
        upsert_email.assert_called_once_with(
            connection,
            self.gmail_account_id,
            self.email,
        )
        index_email.assert_called_once_with(
            connection,
            self.email_id,
            self.email,
            embed_chunks=True,
        )
        connection_context.__exit__.assert_called_once_with(None, None, None)

    @patch("app.worker.index_email")
    @patch("app.worker.upsert_email")
    @patch("app.worker.get_connection")
    def test_indexing_failure_leaves_transaction_context_as_an_error(
        self,
        get_connection,
        upsert_email,
        index_email,
    ):
        connection_context = MagicMock()
        connection = MagicMock()
        get_connection.return_value = connection_context
        connection_context.__enter__.return_value = connection
        upsert_email.return_value = self.email_id
        indexing_error = RuntimeError("embedding failed")
        index_email.side_effect = indexing_error

        with self.assertRaisesRegex(RuntimeError, "embedding failed"):
            process_gmail_message(self.gmail_account_id, self.email)

        exit_args = connection_context.__exit__.call_args.args
        self.assertIs(exit_args[0], RuntimeError)
        self.assertIs(exit_args[1], indexing_error)

    @patch("app.worker.index_email")
    @patch("app.worker.upsert_email")
    @patch("app.worker.get_connection")
    def test_persistence_failure_stops_before_indexing(
        self,
        get_connection,
        upsert_email,
        index_email,
    ):
        connection_context = MagicMock()
        get_connection.return_value = connection_context
        upsert_email.side_effect = ValueError("invalid normalized email")

        with self.assertRaisesRegex(ValueError, "invalid normalized email"):
            process_gmail_message(self.gmail_account_id, self.email)

        index_email.assert_not_called()
        exit_args = connection_context.__exit__.call_args.args
        self.assertIs(exit_args[0], ValueError)

    @patch("app.worker.index_email")
    @patch("app.worker.upsert_email")
    @patch("app.worker.get_connection")
    def test_can_defer_embedding_when_requested(
        self,
        get_connection,
        upsert_email,
        index_email,
    ):
        connection_context = MagicMock()
        connection = MagicMock()
        get_connection.return_value = connection_context
        connection_context.__enter__.return_value = connection
        upsert_email.return_value = self.email_id
        index_email.return_value = 2

        process_gmail_message(
            self.gmail_account_id,
            self.email,
            embed_chunks=False,
        )

        index_email.assert_called_once_with(
            connection,
            self.email_id,
            self.email,
            embed_chunks=False,
        )


if __name__ == "__main__":
    unittest.main()
