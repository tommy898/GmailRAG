import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from google.auth.exceptions import RefreshError

from app import token_crypto
from app.gmail_accounts import (
    GmailAccountNotFoundError,
    IncompleteGmailCredentialsError,
    StoredGmailCredentials,
    get_gmail_sync_checkpoint,
    get_stored_gmail_credentials,
    update_gmail_credentials_after_refresh,
)
from app.gmail_service import (
    GMAIL_READONLY_SCOPE,
    GmailCredentialRefreshError,
    InvalidGmailCredentialScopeError,
    build_gmail_credentials,
    get_authorized_gmail_credentials,
)


class GmailCredentialPersistenceTests(unittest.TestCase):
    def make_database_mocks(self, fetch_result):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.return_value = fetch_result
        return connection, cursor

    @patch("app.gmail_accounts.get_connection")
    def test_loads_saved_history_checkpoint(self, get_connection):
        account_id = uuid.uuid4()
        connection, cursor = self.make_database_mocks(("history-100",))
        get_connection.return_value = connection

        checkpoint = get_gmail_sync_checkpoint(account_id)

        self.assertEqual(checkpoint, "history-100")
        self.assertEqual(cursor.execute.call_args.args[1], (account_id,))

    @patch("app.gmail_accounts.get_connection")
    def test_loads_credentials_for_exact_account_id(self, get_connection):
        account_id = uuid.uuid4()
        profile_id = uuid.uuid4()
        expiry = datetime.now(UTC) + timedelta(hours=1)
        connection, cursor = self.make_database_mocks(
            (
                account_id,
                profile_id,
                "User@Gmail.com",
                "encrypted-access",
                "encrypted-refresh",
                expiry,
                GMAIL_READONLY_SCOPE,
            )
        )
        get_connection.return_value = connection

        stored = get_stored_gmail_credentials(account_id)

        self.assertEqual(stored.account_id, account_id)
        self.assertEqual(stored.profile_id, profile_id)
        self.assertEqual(stored.gmail_address, "user@gmail.com")
        self.assertEqual(cursor.execute.call_args.args[1], (account_id,))

    @patch("app.gmail_accounts.get_connection")
    def test_missing_account_is_rejected(self, get_connection):
        connection, _ = self.make_database_mocks(None)
        get_connection.return_value = connection

        with self.assertRaises(GmailAccountNotFoundError):
            get_stored_gmail_credentials(uuid.uuid4())

    @patch("app.gmail_accounts.get_connection")
    def test_account_without_tokens_must_reconnect(self, get_connection):
        connection, _ = self.make_database_mocks(
            (
                uuid.uuid4(),
                uuid.uuid4(),
                "user@gmail.com",
                None,
                None,
                None,
                GMAIL_READONLY_SCOPE,
            )
        )
        get_connection.return_value = connection

        with self.assertRaises(IncompleteGmailCredentialsError):
            get_stored_gmail_credentials(uuid.uuid4())

    @patch("app.gmail_accounts.get_connection")
    def test_refresh_update_preserves_refresh_token_when_omitted(
        self,
        get_connection,
    ):
        account_id = uuid.uuid4()
        connection, cursor = self.make_database_mocks((account_id,))
        get_connection.return_value = connection

        update_gmail_credentials_after_refresh(
            gmail_account_id=account_id,
            access_token_encrypted="new-encrypted-access",
            refresh_token_encrypted=None,
            token_expires_at=datetime.now(UTC),
        )

        sql, parameters = cursor.execute.call_args.args
        self.assertIn(
            "refresh_token_encrypted = coalesce",
            " ".join(sql.lower().split()),
        )
        self.assertIsNone(parameters[1])
        self.assertEqual(parameters[3], account_id)

    @patch("app.gmail_accounts.get_connection")
    def test_refresh_update_rejects_deleted_account(self, get_connection):
        connection, _ = self.make_database_mocks(None)
        get_connection.return_value = connection

        with self.assertRaises(GmailAccountNotFoundError):
            update_gmail_credentials_after_refresh(
                gmail_account_id=uuid.uuid4(),
                access_token_encrypted="new-encrypted-access",
                refresh_token_encrypted=None,
                token_expires_at=datetime.now(UTC),
            )


class GmailCredentialServiceTests(unittest.TestCase):
    def setUp(self):
        os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
        token_crypto._fernet = None
        self.account_id = uuid.uuid4()
        self.profile_id = uuid.uuid4()

    def tearDown(self):
        token_crypto._fernet = None

    def stored_credentials(
        self,
        *,
        expiry: datetime | None,
        scope: str = GMAIL_READONLY_SCOPE,
    ) -> StoredGmailCredentials:
        return StoredGmailCredentials(
            account_id=self.account_id,
            profile_id=self.profile_id,
            gmail_address="user@gmail.com",
            access_token_encrypted=token_crypto.encrypt_token("access-token"),
            refresh_token_encrypted=token_crypto.encrypt_token("refresh-token"),
            token_expires_at=expiry,
            scope=scope,
        )

    def test_builds_google_credentials_from_encrypted_storage(self):
        expiry = datetime.now(UTC) + timedelta(hours=1)

        credentials = build_gmail_credentials(
            self.stored_credentials(expiry=expiry)
        )

        self.assertEqual(credentials.token, "access-token")
        self.assertEqual(credentials.refresh_token, "refresh-token")
        self.assertEqual(credentials.client_id, "test-client-id")
        self.assertEqual(credentials.client_secret, "test-client-secret")
        self.assertIsNone(credentials.expiry.tzinfo)

    def test_missing_readonly_scope_is_rejected_before_decryption(self):
        with self.assertRaises(InvalidGmailCredentialScopeError):
            build_gmail_credentials(
                self.stored_credentials(
                    expiry=datetime.now(UTC),
                    scope="openid email",
                )
            )

    @patch("app.gmail_service.update_gmail_credentials_after_refresh")
    @patch("app.gmail_service.get_stored_gmail_credentials")
    def test_fresh_access_token_is_reused_without_refresh(
        self,
        get_stored_credentials,
        update_credentials,
    ):
        get_stored_credentials.return_value = self.stored_credentials(
            expiry=datetime.now(UTC) + timedelta(hours=1)
        )

        credentials = get_authorized_gmail_credentials(self.account_id)

        self.assertEqual(credentials.token, "access-token")
        update_credentials.assert_not_called()

    @patch("app.gmail_service.update_gmail_credentials_after_refresh")
    @patch("app.gmail_service.Request")
    @patch("app.gmail_service.get_stored_gmail_credentials")
    def test_expired_access_token_is_refreshed_and_encrypted(
        self,
        get_stored_credentials,
        request_class,
        update_credentials,
    ):
        get_stored_credentials.return_value = self.stored_credentials(
            expiry=datetime.now(UTC) - timedelta(hours=1)
        )
        refreshed_expiry = datetime(2030, 1, 1)

        def refresh(credentials, request):
            self.assertIs(request, request_class.return_value)
            credentials.token = "refreshed-access-token"
            credentials.expiry = refreshed_expiry

        with patch(
            "app.gmail_service.Credentials.refresh",
            autospec=True,
            side_effect=refresh,
        ):
            credentials = get_authorized_gmail_credentials(self.account_id)

        self.assertEqual(credentials.token, "refreshed-access-token")
        arguments = update_credentials.call_args.kwargs
        self.assertEqual(arguments["gmail_account_id"], self.account_id)
        self.assertEqual(
            token_crypto.decrypt_token(arguments["access_token_encrypted"]),
            "refreshed-access-token",
        )
        self.assertIsNone(arguments["refresh_token_encrypted"])
        self.assertEqual(arguments["token_expires_at"].tzinfo, UTC)

    @patch("app.gmail_service.update_gmail_credentials_after_refresh")
    @patch("app.gmail_service.Request")
    @patch("app.gmail_service.get_stored_gmail_credentials")
    def test_rotated_refresh_token_is_encrypted_and_saved(
        self,
        get_stored_credentials,
        request_class,
        update_credentials,
    ):
        get_stored_credentials.return_value = self.stored_credentials(
            expiry=None
        )

        def refresh(credentials, request):
            self.assertIs(request, request_class.return_value)
            credentials.token = "refreshed-access-token"
            credentials._refresh_token = "rotated-refresh-token"
            credentials.expiry = datetime(2030, 1, 1)

        with patch(
            "app.gmail_service.Credentials.refresh",
            autospec=True,
            side_effect=refresh,
        ):
            get_authorized_gmail_credentials(self.account_id)

        arguments = update_credentials.call_args.kwargs
        self.assertEqual(
            token_crypto.decrypt_token(arguments["refresh_token_encrypted"]),
            "rotated-refresh-token",
        )

    @patch("app.gmail_service.update_gmail_credentials_after_refresh")
    @patch("app.gmail_service.Request")
    @patch("app.gmail_service.get_stored_gmail_credentials")
    def test_refresh_failure_does_not_update_database(
        self,
        get_stored_credentials,
        request_class,
        update_credentials,
    ):
        get_stored_credentials.return_value = self.stored_credentials(
            expiry=datetime.now(UTC) - timedelta(hours=1)
        )

        with patch(
            "app.gmail_service.Credentials.refresh",
            autospec=True,
            side_effect=RefreshError("provider-secret-detail"),
        ):
            with self.assertRaises(GmailCredentialRefreshError) as captured:
                get_authorized_gmail_credentials(self.account_id)

        self.assertNotIn("provider-secret-detail", str(captured.exception))
        request_class.assert_called_once_with()
        update_credentials.assert_not_called()


if __name__ == "__main__":
    unittest.main()
