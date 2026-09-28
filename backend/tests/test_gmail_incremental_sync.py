import unittest
import uuid
from unittest.mock import MagicMock, call, patch

from googleapiclient.errors import HttpError

from app.gmail_service import (
    GMAIL_API_NUM_RETRIES,
    GmailApiError,
    GmailHistoryChanges,
    GmailHistoryExpiredError,
    GmailSyncPlan,
    iter_normalized_messages_by_id,
    list_gmail_history_changes,
    prepare_full_gmail_sync,
    prepare_gmail_sync,
    prepare_incremental_gmail_sync,
)


class GmailHistoryListingTests(unittest.TestCase):
    def setUp(self):
        self.service = MagicMock()
        self.history_resource = (
            self.service.users.return_value.history.return_value
        )
        self.list_request = self.history_resource.list.return_value

    def test_lists_all_pages_and_keeps_each_messages_latest_action(self):
        self.list_request.execute.side_effect = [
            {
                "history": [
                    {
                        "messagesAdded": [
                            {"message": {"id": "message-1"}},
                            {"message": {"id": "message-2"}},
                        ]
                    }
                ],
                "nextPageToken": "page-2",
                "historyId": "150",
            },
            {
                "history": [
                    {
                        "messagesDeleted": [
                            {"message": {"id": "message-1"}},
                            {"message": {"id": "message-3"}},
                        ]
                    }
                ],
                "historyId": "200",
            },
        ]

        changes = list_gmail_history_changes(self.service, "100")

        self.assertEqual(
            changes,
            GmailHistoryChanges(
                upsert_message_ids=("message-2",),
                deleted_message_ids=("message-1", "message-3"),
                next_history_id="200",
            ),
        )
        self.assertEqual(
            self.history_resource.list.call_args_list,
            [
                call(
                    userId="me",
                    startHistoryId="100",
                    maxResults=500,
                ),
                call(
                    userId="me",
                    startHistoryId="100",
                    maxResults=500,
                    pageToken="page-2",
                ),
            ],
        )
        self.assertEqual(self.list_request.execute.call_count, 2)
        self.list_request.execute.assert_called_with(
            num_retries=GMAIL_API_NUM_RETRIES
        )

    def test_no_changes_still_returns_new_checkpoint(self):
        self.list_request.execute.return_value = {"historyId": "101"}

        changes = list_gmail_history_changes(self.service, "100")

        self.assertEqual(changes.upsert_message_ids, ())
        self.assertEqual(changes.deleted_message_ids, ())
        self.assertEqual(changes.next_history_id, "101")

    def test_spam_and_trash_label_changes_match_full_sync_filtering(self):
        self.list_request.execute.return_value = {
            "history": [
                {
                    "messagesAdded": [
                        {
                            "message": {
                                "id": "new-spam",
                                "labelIds": ["SPAM"],
                            }
                        }
                    ],
                    "labelsAdded": [
                        {
                            "message": {"id": "moved-to-trash"},
                            "labelIds": ["TRASH"],
                        }
                    ],
                    "labelsRemoved": [
                        {
                            "message": {"id": "restored"},
                            "labelIds": ["TRASH"],
                        },
                        {
                            "message": {
                                "id": "restored-but-still-spam",
                                "labelIds": ["SPAM"],
                            },
                            "labelIds": ["TRASH"],
                        }
                    ],
                }
            ],
            "historyId": "200",
        }

        changes = list_gmail_history_changes(self.service, "100")

        self.assertEqual(
            changes.upsert_message_ids,
            ("restored", "restored-but-still-spam"),
        )
        self.assertEqual(
            changes.deleted_message_ids,
            (
                "new-spam",
                "moved-to-trash",
                "restored",
                "restored-but-still-spam",
            ),
        )

    def test_repeated_history_page_token_is_rejected(self):
        self.list_request.execute.side_effect = [
            {"historyId": "150", "nextPageToken": "same-page"},
            {"historyId": "200", "nextPageToken": "same-page"},
        ]

        with self.assertRaises(GmailApiError):
            list_gmail_history_changes(self.service, "100")

    def test_non_expiration_provider_error_is_sanitized(self):
        response = MagicMock(status=500, reason="provider-secret-detail")
        self.list_request.execute.side_effect = HttpError(
            response,
            b"provider-secret-body",
        )

        with self.assertRaises(GmailApiError) as captured:
            list_gmail_history_changes(self.service, "100")

        self.assertEqual(str(captured.exception), "Gmail history listing failed")
        self.assertNotIn("provider-secret", str(captured.exception))

    def test_malformed_history_message_is_rejected_without_raw_data(self):
        self.list_request.execute.return_value = {
            "history": [
                {
                    "messagesAdded": [
                        {"message": {"threadId": "private-thread"}}
                    ]
                }
            ],
            "historyId": "200",
        }

        with self.assertRaises(GmailApiError) as captured:
            list_gmail_history_changes(self.service, "100")

        self.assertNotIn("private-thread", str(captured.exception))

    def test_expired_checkpoint_has_a_distinct_safe_error(self):
        response = MagicMock(status=404, reason="provider-secret-detail")
        self.list_request.execute.side_effect = HttpError(
            response,
            b"provider-secret-body",
        )

        with self.assertRaises(GmailHistoryExpiredError) as captured:
            list_gmail_history_changes(self.service, "expired-history")

        self.assertNotIn("provider-secret", str(captured.exception))


class GmailSyncPlanningTests(unittest.TestCase):
    @patch("app.gmail_service.get_gmail_message")
    def test_full_message_labels_prevent_spam_or_trash_reindexing(
        self,
        get_message,
    ):
        service = MagicMock()
        get_message.side_effect = [
            {
                "id": "still-spam",
                "labelIds": ["SPAM"],
                "payload": {},
            },
            {
                "id": "restored",
                "labelIds": ["INBOX"],
                "payload": {},
            },
        ]

        messages = list(
            iter_normalized_messages_by_id(
                service,
                iter(["still-spam", "restored"]),
            )
        )

        self.assertEqual(
            [message["gmail_message_id"] for message in messages],
            ["restored"],
        )

    @patch("app.gmail_service.iter_gmail_message_ids")
    @patch("app.gmail_service.get_current_gmail_history_id")
    def test_full_sync_captures_checkpoint_before_streaming_messages(
        self,
        get_history_id,
        iter_message_ids,
    ):
        service = MagicMock()
        get_history_id.return_value = "history-100"
        iter_message_ids.return_value = iter([])

        plan = prepare_full_gmail_sync(service)

        self.assertEqual(plan.mode, "full")
        self.assertEqual(plan.next_history_id, "history-100")
        self.assertEqual(list(plan.messages), [])

    @patch("app.gmail_service.list_gmail_history_changes")
    def test_capped_incremental_sync_does_not_advance_checkpoint(
        self,
        list_changes,
    ):
        service = MagicMock()
        list_changes.return_value = GmailHistoryChanges(
            upsert_message_ids=("message-1", "message-2"),
            deleted_message_ids=("message-deleted",),
            next_history_id="history-200",
        )

        plan = prepare_incremental_gmail_sync(
            service,
            "history-100",
            max_messages=1,
        )

        self.assertEqual(plan.mode, "incremental")
        self.assertIsNone(plan.next_history_id)
        self.assertEqual(plan.deleted_message_ids, ("message-deleted",))

    @patch("app.gmail_service.prepare_full_gmail_sync")
    @patch("app.gmail_service.prepare_incremental_gmail_sync")
    @patch("app.gmail_service.build_gmail_api_service")
    @patch("app.gmail_service.get_authorized_gmail_credentials")
    def test_expired_history_falls_back_to_full_sync(
        self,
        get_credentials,
        build_service,
        prepare_incremental,
        prepare_full,
    ):
        gmail_account_id = uuid.uuid4()
        service = MagicMock()
        expected_plan = GmailSyncPlan(
            mode="full",
            messages=iter([]),
            deleted_message_ids=(),
            next_history_id="history-300",
        )
        build_service.return_value = service
        prepare_incremental.side_effect = GmailHistoryExpiredError(
            "checkpoint expired"
        )
        prepare_full.return_value = expected_plan

        plan = prepare_gmail_sync(
            gmail_account_id,
            "history-100",
        )

        self.assertIs(plan, expected_plan)
        get_credentials.assert_called_once_with(gmail_account_id)
        prepare_incremental.assert_called_once_with(
            service,
            "history-100",
            max_messages=None,
        )
        prepare_full.assert_called_once_with(
            service,
            max_messages=None,
        )


if __name__ == "__main__":
    unittest.main()
