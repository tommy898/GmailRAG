import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.auth import InvalidAccessTokenError, verify_supabase_access_token
from app.main import app
from app.schemas import AskResponse


class SupabaseJwtVerificationTests(unittest.TestCase):
    def setUp(self):
        self.supabase_url = "https://test-project.supabase.co"
        self.issuer = f"{self.supabase_url}/auth/v1"
        self.profile_id = uuid.uuid4()
        self.private_key = ec.generate_private_key(ec.SECP256R1())
        self.public_key = self.private_key.public_key()
        self.environment_patch = patch.dict(
            os.environ,
            {"SUPABASE_URL": self.supabase_url},
        )
        self.environment_patch.start()

    def tearDown(self):
        self.environment_patch.stop()

    def claims(self) -> dict:
        return {
            "sub": str(self.profile_id),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "iss": self.issuer,
            "aud": "authenticated",
            "role": "authenticated",
        }

    def encode(self, claims: dict) -> str:
        return jwt.encode(
            claims,
            self.private_key,
            algorithm="ES256",
            headers={"kid": "test-key"},
        )

    def verify(self, claims: dict) -> uuid.UUID:
        jwks_client = MagicMock()
        jwks_client.get_signing_key_from_jwt.return_value = SimpleNamespace(
            key=self.public_key
        )

        with patch("app.auth.get_jwks_client", return_value=jwks_client):
            return verify_supabase_access_token(self.encode(claims))

    def assert_rejected(self, claims: dict):
        with self.assertRaises(InvalidAccessTokenError):
            self.verify(claims)

    def test_valid_token_returns_profile_uuid(self):
        self.assertEqual(self.verify(self.claims()), self.profile_id)

    def test_wrong_issuer_is_rejected(self):
        claims = self.claims()
        claims["iss"] = "https://other-project.supabase.co/auth/v1"
        self.assert_rejected(claims)

    def test_wrong_audience_is_rejected(self):
        claims = self.claims()
        claims["aud"] = "anonymous"
        self.assert_rejected(claims)

    def test_expired_token_is_rejected(self):
        claims = self.claims()
        claims["exp"] = datetime.now(UTC) - timedelta(minutes=1)
        self.assert_rejected(claims)

    def test_wrong_role_is_rejected(self):
        claims = self.claims()
        claims["role"] = "service_role"
        self.assert_rejected(claims)

    def test_missing_subject_is_rejected(self):
        claims = self.claims()
        del claims["sub"]
        self.assert_rejected(claims)

    def test_malformed_subject_is_rejected(self):
        claims = self.claims()
        claims["sub"] = "not-a-uuid"
        self.assert_rejected(claims)


class ProtectedRouteTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.profile_id = uuid.uuid4()
        self.authorization_header = {"Authorization": "Bearer test-token"}

    @patch("app.main.build_gmail_authorization_url")
    @patch("app.main.answer_question")
    def test_missing_token_returns_401_before_protected_work(
        self,
        answer_question,
        build_authorization_url,
    ):
        ask_response = self.client.post(
            "/ask",
            json={"question": "private question"},
        )
        connect_response = self.client.get("/gmail/connect")

        self.assertEqual(ask_response.status_code, 401)
        self.assertEqual(connect_response.status_code, 401)
        self.assertEqual(ask_response.headers["www-authenticate"], "Bearer")
        self.assertEqual(connect_response.headers["www-authenticate"], "Bearer")
        answer_question.assert_not_called()
        build_authorization_url.assert_not_called()

    @patch("app.main.build_gmail_authorization_url")
    @patch("app.main.answer_question")
    @patch("app.auth.verify_supabase_access_token")
    def test_invalid_token_returns_401_before_protected_work(
        self,
        verify_token,
        answer_question,
        build_authorization_url,
    ):
        verify_token.side_effect = InvalidAccessTokenError

        ask_response = self.client.post(
            "/ask",
            json={"question": "private question"},
            headers=self.authorization_header,
        )
        connect_response = self.client.get(
            "/gmail/connect",
            headers=self.authorization_header,
        )

        self.assertEqual(ask_response.status_code, 401)
        self.assertEqual(connect_response.status_code, 401)
        answer_question.assert_not_called()
        build_authorization_url.assert_not_called()

    @patch("app.main.answer_question")
    @patch("app.auth.verify_supabase_access_token")
    def test_ask_passes_authenticated_profile_to_rag(
        self,
        verify_token,
        answer_question,
    ):
        verify_token.return_value = self.profile_id
        answer_question.return_value = AskResponse(
            answer="isolated answer",
            sources=[],
        )

        response = self.client.post(
            "/ask",
            json={"question": "private question"},
            headers=self.authorization_header,
        )

        self.assertEqual(response.status_code, 200)
        answer_question.assert_called_once_with(
            "private question",
            self.profile_id,
        )

    @patch("app.main.build_gmail_authorization_url")
    @patch("app.auth.verify_supabase_access_token")
    def test_connect_uses_profile_and_exposes_no_tokens(
        self,
        verify_token,
        build_authorization_url,
    ):
        verify_token.return_value = self.profile_id
        build_authorization_url.return_value = (
            "https://accounts.google.com/o/oauth2/auth?state=encrypted-state"
        )

        response = self.client.get(
            "/gmail/connect",
            headers=self.authorization_header,
        )

        self.assertEqual(response.status_code, 200)
        build_authorization_url.assert_called_once_with(self.profile_id)
        self.assertEqual(
            set(response.json()),
            {"authorization_url"},
        )
        self.assertNotIn("access_token", response.text)
        self.assertNotIn("refresh_token", response.text)
        self.assertNotIn("client_secret", response.text)


if __name__ == "__main__":
    unittest.main()
