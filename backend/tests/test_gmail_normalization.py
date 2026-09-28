import base64
import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import patch

from app.gmail_service import (
    GmailMessageNormalizationError,
    iter_normalized_gmail_messages,
    normalize_gmail_message,
)


def encode_body(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


class GmailMessageNormalizationTests(unittest.TestCase):
    def test_normalizes_plain_text_message(self):
        message = {
            "id": "message-1",
            "threadId": "thread-1",
            "internalDate": "1704067200000",
            "snippet": " Message preview ",
            "payload": {
                "mimeType": "text/plain",
                "headers": [
                    {"name": "From", "value": "Sender <sender@example.com>"},
                    {"name": "To", "value": "user@example.com"},
                    {"name": "Subject", "value": "Test subject"},
                    {
                        "name": "Date",
                        "value": "Mon, 1 Jan 2024 00:00:00 +0000",
                    },
                ],
                "body": {
                    "data": encode_body("Hello\u00a0there\n\nSecond   line")
                },
            },
        }

        normalized = normalize_gmail_message(message)

        self.assertEqual(normalized["gmail_message_id"], "message-1")
        self.assertEqual(normalized["gmail_thread_id"], "thread-1")
        self.assertEqual(
            normalized["from_email"],
            "Sender <sender@example.com>",
        )
        self.assertEqual(normalized["to_email"], "user@example.com")
        self.assertEqual(normalized["subject"], "Test subject")
        self.assertEqual(
            normalized["sent_at"],
            datetime(2024, 1, 1, tzinfo=UTC),
        )
        self.assertEqual(normalized["snippet"], "Message preview")
        self.assertEqual(normalized["body_text"], "Hello there\n\nSecond line")

    def test_nested_multipart_prefers_plain_text_and_skips_attachment(self):
        message = {
            "id": "message-1",
            "payload": {
                "mimeType": "multipart/mixed",
                "headers": [],
                "parts": [
                    {
                        "mimeType": "multipart/alternative",
                        "parts": [
                            {
                                "mimeType": "text/html",
                                "body": {
                                    "data": encode_body("<p>HTML version</p>")
                                },
                            },
                            {
                                "mimeType": "text/plain",
                                "body": {"data": encode_body("Plain version")},
                            },
                        ],
                    },
                    {
                        "mimeType": "text/plain",
                        "filename": "private-attachment.txt",
                        "body": {"data": encode_body("Attachment contents")},
                    },
                ],
            },
        }

        normalized = normalize_gmail_message(message)

        self.assertEqual(normalized["body_text"], "Plain version")
        self.assertNotIn("Attachment", normalized["body_text"])
        self.assertNotIn("HTML version", normalized["body_text"])

    def test_html_only_message_uses_readable_fallback(self):
        html = """
        <html>
          <head><style>.hidden { display: none; }</style></head>
          <body>
            <h1>Hello &amp; welcome</h1>
            <p>First line<br>Second line</p>
            <script>privateScriptValue()</script>
          </body>
        </html>
        """
        message = {
            "id": "message-1",
            "payload": {
                "mimeType": "text/html",
                "headers": [],
                "body": {"data": encode_body(html)},
            },
        }

        normalized = normalize_gmail_message(message)

        self.assertIn("Hello & welcome", normalized["body_text"])
        self.assertIn("First line", normalized["body_text"])
        self.assertIn("Second line", normalized["body_text"])
        self.assertNotIn("display: none", normalized["body_text"])
        self.assertNotIn("privateScriptValue", normalized["body_text"])

    def test_decodes_encoded_email_headers(self):
        message = {
            "id": "message-1",
            "payload": {
                "headers": [
                    {
                        "name": "Subject",
                        "value": "=?utf-8?q?Hello_=E2=9C=93?=",
                    }
                ]
            },
        }

        normalized = normalize_gmail_message(message)

        self.assertEqual(normalized["subject"], "Hello ✓")

    def test_date_header_is_timestamp_fallback(self):
        message = {
            "id": "message-1",
            "internalDate": "not-a-timestamp",
            "payload": {
                "headers": [
                    {
                        "name": "Date",
                        "value": "Sun, 31 Dec 2023 16:00:00 -0800",
                    }
                ]
            },
        }

        normalized = normalize_gmail_message(message)

        self.assertEqual(
            normalized["sent_at"],
            datetime(2024, 1, 1, tzinfo=UTC),
        )

    def test_missing_message_id_is_rejected(self):
        with self.assertRaises(GmailMessageNormalizationError):
            normalize_gmail_message({"payload": {}})

    def test_invalid_body_encoding_is_rejected_without_exposing_data(self):
        message = {
            "id": "message-1",
            "payload": {
                "mimeType": "text/plain",
                "body": {"data": "provider-secret-%%%"},
            },
        }

        with self.assertRaises(GmailMessageNormalizationError) as captured:
            normalize_gmail_message(message)

        self.assertNotIn("provider-secret", str(captured.exception))

    @patch("app.gmail_service.iter_gmail_messages")
    def test_normalized_iterator_preserves_streaming(self, iter_messages):
        account_id = uuid.uuid4()
        iter_messages.return_value = iter(
            [
                {"id": "message-1", "payload": {}},
                {"id": "message-2", "payload": {}},
            ]
        )

        normalized = list(
            iter_normalized_gmail_messages(
                account_id,
                query="newer_than:1y",
                max_messages=2,
            )
        )

        self.assertEqual(
            [message["gmail_message_id"] for message in normalized],
            ["message-1", "message-2"],
        )
        iter_messages.assert_called_once_with(
            account_id,
            query="newer_than:1y",
            max_messages=2,
            include_spam_trash=False,
        )


if __name__ == "__main__":
    unittest.main()
