import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.ingestion import (
    delete_email,
    delete_emails_missing_from_full_sync,
    upsert_email,
)


class EmailIngestionTests(unittest.TestCase):
    def test_upsert_persists_every_normalized_email_field(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        email_id = uuid.uuid4()
        gmail_account_id = uuid.uuid4()
        sent_at = datetime(2024, 1, 1, tzinfo=UTC)
        cursor.fetchone.return_value = (email_id,)
        email = {
            "gmail_message_id": "message-1",
            "gmail_thread_id": "thread-1",
            "from_email": "sender@example.com",
            "to_email": "user@example.com",
            "subject": "Subject",
            "sent_at": sent_at,
            "gmail_date_raw": "Mon, 1 Jan 2024 00:00:00 +0000",
            "snippet": "Preview",
            "body_text": "Message body",
        }

        result = upsert_email(connection, gmail_account_id, email)

        self.assertEqual(result, email_id)
        sql, parameters = cursor.execute.call_args.args
        normalized_sql = " ".join(sql.split())
        self.assertIn("sent_at", normalized_sql)
        self.assertIn("sent_at = excluded.sent_at", normalized_sql)
        self.assertEqual(
            parameters,
            (
                gmail_account_id,
                "message-1",
                "thread-1",
                "sender@example.com",
                "user@example.com",
                "Subject",
                sent_at,
                "Mon, 1 Jan 2024 00:00:00 +0000",
                "Preview",
                "Message body",
            ),
        )

    def test_deletes_one_message_within_its_gmail_account(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        gmail_account_id = uuid.uuid4()
        cursor.fetchone.return_value = (uuid.uuid4(),)

        deleted = delete_email(
            connection,
            gmail_account_id,
            "message-1",
        )

        self.assertTrue(deleted)
        sql, parameters = cursor.execute.call_args.args
        self.assertIn(
            "where gmail_account_id = %s",
            " ".join(sql.split()),
        )
        self.assertEqual(parameters, (gmail_account_id, "message-1"))

    def test_full_sync_deletes_only_messages_missing_from_gmail(self):
        connection = MagicMock()
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.rowcount = 2
        gmail_account_id = uuid.uuid4()

        deleted_count = delete_emails_missing_from_full_sync(
            connection,
            gmail_account_id,
            ["message-1", "message-2"],
        )

        self.assertEqual(deleted_count, 2)
        sql, parameters = cursor.execute.call_args.args
        normalized_sql = " ".join(sql.split())
        self.assertIn("gmail_account_id = %s", normalized_sql)
        self.assertIn("gmail_message_id = any(%s::text[])", normalized_sql)
        self.assertEqual(
            parameters,
            (gmail_account_id, ["message-1", "message-2"]),
        )


if __name__ == "__main__":
    unittest.main()
