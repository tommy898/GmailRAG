import json
import logging
import os
import unittest
import uuid
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from google.oauth2.credentials import Credentials

from app import token_crypto
from app.gmail_accounts import (
    MissingRefreshTokenError,
    ProfileNotFoundError,
    upsert_gmail_account_credentials,
)
from app.gmail_oauth import (
    GMAIL_READONLY_SCOPE,
    GmailAccountMismatchError,
    GmailOAuthExchangeError,
    InvalidGmailOAuthStateError,
    MissingGmailScopeError,
    build_gmail_authorization_url,
    complete_gmail_connection,
    create_gmail_oauth_state,
    parse_gmail_oauth_state,
)
from app.gmail_service import GmailProfileError
from app.main import RedactOAuthCallbackQueryFilter, app


class OAuthAccessLogTests(unittest.TestCase):
    def test_callback_query_is_redacted(self):
        record = logging.LogRecord(
            name="uvicorn.access",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='%s - "%s %s HTTP/%s" %d',
            args=(
                "127.0.0.1:12345",
                "GET",
                "/gmail/callback?code=secret-code&state=secret-state",
                "1.1",
                303,
            ),
            exc_info=None,
        )

        RedactOAuthCallbackQueryFilter().filter(record)
        rendered_message = record.getMessage()

        self.assertIn("/gmail/callback?[redacted]", rendered_message)
        self.assertNotIn("secret-code", rendered_message)
        self.assertNotIn("secret-state", rendered_message)


class GmailOAuthStateTests(unittest.TestCase):
    def setUp(self):
        os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        os.environ["GOOGLE_CLIENT_ID"] = "test-client-id"
        os.environ["GOOGLE_CLIENT_SECRET"] = "test-client-secret"
        os.environ["GOOGLE_REDIRECT_URI"] = (
            "http://localhost:8000/gmail/callback"
        )
        token_crypto._fernet = None

    def tearDown(self):
        token_crypto._fernet = None

    def test_state_round_trip_returns_profile_id(self):
        profile_id = uuid.uuid4()
        code_verifier = "v" * 64

        state = create_gmail_oauth_state(profile_id, code_verifier)
        parsed_state = parse_gmail_oauth_state(state)

        self.assertEqual(parsed_state.profile_id, profile_id)
        self.assertEqual(parsed_state.code_verifier, code_verifier)

    def test_modified_state_is_rejected(self):
        state = create_gmail_oauth_state(uuid.uuid4(), "v" * 64)
        modified_state = state[:-1] + ("A" if state[-1] != "A" else "B")

        with self.assertRaises(InvalidGmailOAuthStateError):
            parse_gmail_oauth_state(modified_state)

    def test_authorization_requests_only_the_gmail_scope(self):
        authorization_url = build_gmail_authorization_url(uuid.uuid4())
        parameters = parse_qs(urlparse(authorization_url).query)

        self.assertEqual(parameters["include_granted_scopes"], ["false"])
        self.assertEqual(parameters["scope"], [GMAIL_READONLY_SCOPE])
        self.assertEqual(parameters["code_challenge_method"], ["S256"])

        parsed_state = parse_gmail_oauth_state(parameters["state"][0])
        self.assertTrue(parsed_state.code_verifier)

    def test_expired_state_is_rejected(self):
        payload = json.dumps(
            {
                "purpose": "gmail_oauth",
                "profile_id": str(uuid.uuid4()),
                "nonce": "test-nonce",
                "code_verifier": "v" * 64,
            }
        ).encode()
        expired_state = token_crypto.get_token_cipher().encrypt_at_time(
            payload,
            current_time=0,
        ).decode()

        with self.assertRaises(InvalidGmailOAuthStateError):
            parse_gmail_oauth_state(expired_state)


class GmailConnectionTests(unittest.TestCase):
    def setUp(self):
        os.environ["TOKEN_ENCRYPTION_KEY"] = Fernet.generate_key().decode()
        token_crypto._fernet = None
        self.profile_id = uuid.uuid4()
        self.account_id = uuid.uuid4()

    def tearDown(self):
        token_crypto._fernet = None

    def make_credentials(
        self,
        *,
        scopes: list[str] | None = None,
        refresh_token: str | None = "refresh-token",
    ) -> Credentials:
        granted_scopes = scopes if scopes is not None else [GMAIL_READONLY_SCOPE]
        return Credentials(
            token="access-token",
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id="test-client-id",
            client_secret="test-client-secret",
            scopes=[GMAIL_READONLY_SCOPE],
            granted_scopes=granted_scopes,
            expiry=datetime(2030, 1, 1),
        )

    @patch("app.gmail_oauth.upsert_gmail_account_credentials")
    @patch("app.gmail_oauth.get_gmail_address")
    @patch("app.gmail_oauth.exchange_gmail_authorization_code")
    @patch("app.gmail_oauth.get_profile_email")
    @patch("app.gmail_oauth.parse_gmail_oauth_state")
    def test_success_encrypts_tokens_and_persists_account(
        self,
        parse_state,
        get_profile_email,
        exchange_code,
        get_gmail_address,
        upsert_account,
    ):
        parse_state.return_value.profile_id = self.profile_id
        parse_state.return_value.code_verifier = "v" * 64
        get_profile_email.return_value = "user@gmail.com"
        exchange_code.return_value = self.make_credentials()
        get_gmail_address.return_value = "user@gmail.com"
        upsert_account.return_value = self.account_id

        result = complete_gmail_connection("code", "state")

        self.assertEqual(result, self.account_id)
        exchange_code.assert_called_once_with("code", "state", "v" * 64)
        arguments = upsert_account.call_args.kwargs
        self.assertNotEqual(arguments["access_token_encrypted"], "access-token")
        self.assertNotEqual(arguments["refresh_token_encrypted"], "refresh-token")
        self.assertEqual(
            token_crypto.decrypt_token(arguments["access_token_encrypted"]),
            "access-token",
        )
        self.assertEqual(
            token_crypto.decrypt_token(arguments["refresh_token_encrypted"]),
            "refresh-token",
        )
        self.assertEqual(arguments["token_expires_at"].tzinfo, UTC)
        self.assertEqual(arguments["scope"], GMAIL_READONLY_SCOPE)

    @patch("app.gmail_oauth.upsert_gmail_account_credentials")
    @patch("app.gmail_oauth.get_gmail_address")
    @patch("app.gmail_oauth.exchange_gmail_authorization_code")
    @patch("app.gmail_oauth.get_profile_email")
    @patch("app.gmail_oauth.parse_gmail_oauth_state")
    def test_account_mismatch_writes_nothing(
        self,
        parse_state,
        get_profile_email,
        exchange_code,
        get_gmail_address,
        upsert_account,
    ):
        parse_state.return_value.profile_id = self.profile_id
        parse_state.return_value.code_verifier = "v" * 64
        get_profile_email.return_value = "signed-in@gmail.com"
        exchange_code.return_value = self.make_credentials()
        get_gmail_address.return_value = "different@gmail.com"

        with self.assertRaises(GmailAccountMismatchError):
            complete_gmail_connection("code", "state")

        upsert_account.assert_not_called()

    @patch("app.gmail_oauth.upsert_gmail_account_credentials")
    @patch("app.gmail_oauth.get_gmail_address")
    @patch("app.gmail_oauth.exchange_gmail_authorization_code")
    @patch("app.gmail_oauth.get_profile_email")
    @patch("app.gmail_oauth.parse_gmail_oauth_state")
    def test_missing_scope_writes_nothing(
        self,
        parse_state,
        get_profile_email,
        exchange_code,
        get_gmail_address,
        upsert_account,
    ):
        parse_state.return_value.profile_id = self.profile_id
        parse_state.return_value.code_verifier = "v" * 64
        get_profile_email.return_value = "user@gmail.com"
        exchange_code.return_value = self.make_credentials(scopes=[])

        with self.assertRaises(MissingGmailScopeError):
            complete_gmail_connection("code", "state")

        get_gmail_address.assert_not_called()
        upsert_account.assert_not_called()

    @patch("app.gmail_oauth.exchange_gmail_authorization_code")
    @patch("app.gmail_oauth.get_profile_email")
    @patch("app.gmail_oauth.parse_gmail_oauth_state")
    def test_missing_profile_stops_before_google_exchange(
        self,
        parse_state,
        get_profile_email,
        exchange_code,
    ):
        parse_state.return_value.profile_id = self.profile_id
        parse_state.return_value.code_verifier = "v" * 64
        get_profile_email.side_effect = ProfileNotFoundError

        with self.assertRaises(ProfileNotFoundError):
            complete_gmail_connection("code", "state")

        exchange_code.assert_not_called()

    @patch("app.gmail_oauth.upsert_gmail_account_credentials")
    @patch("app.gmail_oauth.get_gmail_address")
    @patch("app.gmail_oauth.exchange_gmail_authorization_code")
    @patch("app.gmail_oauth.get_profile_email")
    @patch("app.gmail_oauth.parse_gmail_oauth_state")
    def test_token_exchange_failure_writes_nothing(
        self,
        parse_state,
        get_profile_email,
        exchange_code,
        get_gmail_address,
        upsert_account,
    ):
        parse_state.return_value.profile_id = self.profile_id
        parse_state.return_value.code_verifier = "v" * 64
        get_profile_email.return_value = "user@gmail.com"
        exchange_code.side_effect = GmailOAuthExchangeError

        with self.assertRaises(GmailOAuthExchangeError):
            complete_gmail_connection("code", "state")

        get_gmail_address.assert_not_called()
        upsert_account.assert_not_called()

    @patch("app.gmail_oauth.upsert_gmail_account_credentials")
    @patch("app.gmail_oauth.get_gmail_address")
    @patch("app.gmail_oauth.exchange_gmail_authorization_code")
    @patch("app.gmail_oauth.get_profile_email")
    @patch("app.gmail_oauth.parse_gmail_oauth_state")
    def test_gmail_profile_failure_writes_nothing(
        self,
        parse_state,
        get_profile_email,
        exchange_code,
        get_gmail_address,
        upsert_account,
    ):
        parse_state.return_value.profile_id = self.profile_id
        parse_state.return_value.code_verifier = "v" * 64
        get_profile_email.return_value = "user@gmail.com"
        exchange_code.return_value = self.make_credentials()
        get_gmail_address.side_effect = GmailProfileError

        with self.assertRaises(GmailProfileError):
            complete_gmail_connection("code", "state")

        upsert_account.assert_not_called()


class GmailAccountPersistenceTests(unittest.TestCase):
    def make_database_mocks(self, fetch_results):
        connection = MagicMock()
        connection.__enter__.return_value = connection
        cursor = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        cursor.fetchone.side_effect = fetch_results
        return connection, cursor

    @patch("app.gmail_accounts.get_connection")
    def test_new_account_requires_refresh_token(self, get_connection):
        connection, cursor = self.make_database_mocks([None])
        get_connection.return_value = connection

        with self.assertRaises(MissingRefreshTokenError):
            upsert_gmail_account_credentials(
                profile_id=uuid.uuid4(),
                gmail_address="user@gmail.com",
                access_token_encrypted="encrypted-access",
                refresh_token_encrypted=None,
                token_expires_at=None,
                scope=GMAIL_READONLY_SCOPE,
            )

        self.assertEqual(cursor.execute.call_count, 1)

    @patch("app.gmail_accounts.get_connection")
    def test_reconnection_preserves_existing_refresh_token(self, get_connection):
        account_id = uuid.uuid4()
        connection, cursor = self.make_database_mocks(
            [("existing-encrypted-refresh",), (account_id,)]
        )
        get_connection.return_value = connection

        result = upsert_gmail_account_credentials(
            profile_id=uuid.uuid4(),
            gmail_address="user@gmail.com",
            access_token_encrypted="new-encrypted-access",
            refresh_token_encrypted=None,
            token_expires_at=None,
            scope=GMAIL_READONLY_SCOPE,
        )

        self.assertEqual(result, account_id)
        upsert_parameters = cursor.execute.call_args_list[1].args[1]
        self.assertEqual(upsert_parameters[3], "existing-encrypted-refresh")
        upsert_sql = cursor.execute.call_args_list[1].args[0].lower()
        self.assertNotIn("last_history_id", upsert_sql)
        self.assertNotIn("last_synced_at", upsert_sql)
        self.assertNotIn("delete", upsert_sql)


class GmailCallbackRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.frontend_patch = patch(
            "app.main.get_frontend_url",
            return_value="http://localhost:3000",
        )
        self.frontend_patch.start()

    def tearDown(self):
        self.frontend_patch.stop()

    def callback(self, query: str):
        return self.client.get(
            f"/gmail/callback{query}",
            follow_redirects=False,
        )

    def test_missing_state_redirects_with_invalid_state(self):
        response = self.callback("?code=test-code")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:3000/?gmail_error=invalid_state",
        )

    @patch("app.main.complete_gmail_connection")
    def test_missing_code_does_not_start_connection(self, complete_connection):
        response = self.callback("?state=test-state")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:3000/?gmail_error=connection_failed",
        )
        complete_connection.assert_not_called()

    @patch("app.main.complete_gmail_connection")
    def test_denied_consent_does_not_exchange_code(self, complete_connection):
        response = self.callback("?error=access_denied&state=test-state")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:3000/?gmail_error=access_denied",
        )
        complete_connection.assert_not_called()

    @patch("app.main.complete_gmail_connection")
    def test_success_redirects_to_frontend(self, complete_connection):
        response = self.callback("?code=test-code&state=test-state")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:3000/?gmail=connected",
        )
        complete_connection.assert_called_once_with("test-code", "test-state")

    @patch("app.main.complete_gmail_connection")
    def test_account_mismatch_redirects_with_sanitized_error(
        self,
        complete_connection,
    ):
        complete_connection.side_effect = GmailAccountMismatchError

        response = self.callback("?code=secret-code&state=secret-state")

        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:3000/?gmail_error=account_mismatch",
        )
        self.assertNotIn("secret-code", response.headers["location"])
        self.assertNotIn("secret-state", response.headers["location"])

    @patch("app.main.complete_gmail_connection")
    def test_expected_failure_does_not_log_provider_details(
        self,
        complete_connection,
    ):
        complete_connection.side_effect = GmailOAuthExchangeError(
            "provider-secret-detail"
        )

        with self.assertLogs("app.main", level="WARNING") as captured_logs:
            response = self.callback(
                "?code=secret-code&state=secret-state"
            )

        rendered_logs = " ".join(captured_logs.output)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:3000/?gmail_error=connection_failed",
        )
        self.assertNotIn("provider-secret-detail", rendered_logs)
        self.assertNotIn("secret-code", rendered_logs)
        self.assertNotIn("secret-state", rendered_logs)

    @patch("app.main.complete_gmail_connection")
    def test_unexpected_failure_is_sanitized(self, complete_connection):
        complete_connection.side_effect = RuntimeError(
            "unexpected-provider-secret"
        )

        with self.assertLogs("app.main", level="ERROR") as captured_logs:
            response = self.callback(
                "?code=secret-code&state=secret-state"
            )

        rendered_logs = " ".join(captured_logs.output)
        self.assertEqual(response.status_code, 303)
        self.assertEqual(
            response.headers["location"],
            "http://localhost:3000/?gmail_error=connection_failed",
        )
        self.assertNotIn("unexpected-provider-secret", rendered_logs)
        self.assertNotIn("secret-code", rendered_logs)
        self.assertNotIn("secret-state", rendered_logs)


if __name__ == "__main__":
    unittest.main()
