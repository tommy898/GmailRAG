import unittest
import uuid
from unittest.mock import MagicMock, call, patch

from googleapiclient.errors import HttpError

from app.gmail_service import (
    GMAIL_API_NUM_RETRIES,
    GmailApiError,
    get_gmail_message,
    iter_gmail_message_ids,
    iter_gmail_messages,
)


class GmailMessageListingTests(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.messages_resource = self.service.users.return_value.messages.return_value
        self.list_request = self.messages_resource.list.return_value

    def test_lists_all_message_ids_across_pages(self):
        self.list_request.execute.side_effect = [
            {
                "messages": [{"id": "message-1"}, {"id": "message-2"}],
                "nextPageToken": "page-2",
            },
            {"messages": [{"id": "message-3"}]},
        ]

        message_ids = list(iter_gmail_message_ids(self.service))

        self.assertEqual(
            message_ids,
            ["message-1", "message-2", "message-3"],
        )
        self.assertEqual(
            self.messages_resource.list.call_args_list,
            [
                call(
                    userId="me",
                    maxResults=500,
                    includeSpamTrash=False,
                ),
                call(
                    userId="me",
                    maxResults=500,
                    includeSpamTrash=False,
                    pageToken="page-2",
                ),
            ],
        )
        self.assertEqual(self.list_request.execute.call_count, 2)
        self.list_request.execute.assert_called_with(
            num_retries=GMAIL_API_NUM_RETRIES
        )

    def test_message_cap_changes_page_size_and_stops_listing(self):
        self.list_request.execute.side_effect = [
            {
                "messages": [{"id": "message-1"}, {"id": "message-2"}],
                "nextPageToken": "page-2",
            },
            {
                "messages": [{"id": "message-3"}],
                "nextPageToken": "unused-page",
            },
        ]

        message_ids = list(
            iter_gmail_message_ids(
                self.service,
                query=" newer_than:1y ",
                max_messages=3,
            )
        )

        self.assertEqual(
            message_ids,
            ["message-1", "message-2", "message-3"],
        )
        self.assertEqual(
            self.messages_resource.list.call_args_list[0],
            call(
                userId="me",
                maxResults=3,
                includeSpamTrash=False,
                q="newer_than:1y",
            ),
        )
        self.assertEqual(
            self.messages_resource.list.call_args_list[1],
            call(
                userId="me",
                maxResults=1,
                includeSpamTrash=False,
                q="newer_than:1y",
                pageToken="page-2",
            ),
        )

    def test_zero_cap_makes_no_api_request(self):
        self.assertEqual(
            list(iter_gmail_message_ids(self.service, max_messages=0)),
            [],
        )
        self.messages_resource.list.assert_not_called()

    def test_negative_cap_is_rejected(self):
        with self.assertRaises(ValueError):
            list(iter_gmail_message_ids(self.service, max_messages=-1))

    def test_repeated_page_token_is_rejected(self):
        self.list_request.execute.side_effect = [
            {"messages": [], "nextPageToken": "same-page"},
            {"messages": [], "nextPageToken": "same-page"},
        ]

        with self.assertRaises(GmailApiError):
            list(iter_gmail_message_ids(self.service))

    def test_message_without_id_is_rejected(self):
        self.list_request.execute.return_value = {"messages": [{}]}

        with self.assertRaises(GmailApiError):
            list(iter_gmail_message_ids(self.service))

    def test_provider_error_is_sanitized(self):
        response = MagicMock(status=500, reason="provider-secret-detail")
        self.list_request.execute.side_effect = HttpError(
            response,
            b"provider-secret-body",
        )

        with self.assertRaises(GmailApiError) as captured:
            list(iter_gmail_message_ids(self.service))

        self.assertEqual(str(captured.exception), "Gmail message listing failed")
        self.assertNotIn("provider-secret", str(captured.exception))


class GmailMessageDownloadTests(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.messages_resource = self.service.users.return_value.messages.return_value
        self.get_request = self.messages_resource.get.return_value

    def test_downloads_full_message(self):
        full_message = {
            "id": "message-1",
            "threadId": "thread-1",
            "payload": {"mimeType": "text/plain"},
        }
        self.get_request.execute.return_value = full_message

        result = get_gmail_message(self.service, "message-1")

        self.assertIs(result, full_message)
        self.messages_resource.get.assert_called_once_with(
            userId="me",
            id="message-1",
            format="full",
        )
        self.get_request.execute.assert_called_once_with(
            num_retries=GMAIL_API_NUM_RETRIES
        )

    def test_invalid_download_is_rejected(self):
        self.get_request.execute.return_value = {"threadId": "thread-1"}

        with self.assertRaises(GmailApiError):
            get_gmail_message(self.service, "message-1")

    def test_provider_error_is_sanitized(self):
        response = MagicMock(status=404, reason="provider-secret-detail")
        self.get_request.execute.side_effect = HttpError(
            response,
            b"provider-secret-body",
        )

        with self.assertRaises(GmailApiError) as captured:
            get_gmail_message(self.service, "message-1")

        self.assertEqual(str(captured.exception), "Gmail message download failed")
        self.assertNotIn("provider-secret", str(captured.exception))

    @patch("app.gmail_service.get_gmail_message")
    @patch("app.gmail_service.iter_gmail_message_ids")
    @patch("app.gmail_service.build_gmail_api_service")
    @patch("app.gmail_service.get_authorized_gmail_credentials")
    def test_account_iterator_reuses_one_service_for_all_messages(
        self,
        get_credentials,
        build_service,
        iter_message_ids,
        get_message,
    ):
        account_id = uuid.uuid4()
        credentials = MagicMock()
        service = MagicMock()
        get_credentials.return_value = credentials
        build_service.return_value = service
        iter_message_ids.return_value = iter(["message-1", "message-2"])
        get_message.side_effect = [
            {"id": "message-1"},
            {"id": "message-2"},
        ]

        messages = list(
            iter_gmail_messages(
                account_id,
                query="newer_than:1y",
                max_messages=2,
            )
        )

        self.assertEqual(
            messages,
            [{"id": "message-1"}, {"id": "message-2"}],
        )
        get_credentials.assert_called_once_with(account_id)
        build_service.assert_called_once_with(credentials)
        iter_message_ids.assert_called_once_with(
            service,
            query="newer_than:1y",
            max_messages=2,
            include_spam_trash=False,
        )
        get_message.assert_has_calls(
            [
                call(service, "message-1"),
                call(service, "message-2"),
            ]
        )


if __name__ == "__main__":
    unittest.main()
