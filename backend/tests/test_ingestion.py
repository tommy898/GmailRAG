import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock

from app.ingestion import upsert_email


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


if __name__ == "__main__":
    unittest.main()
