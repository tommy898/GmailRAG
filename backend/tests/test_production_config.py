import os
import traceback
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import (
    ConfigurationError,
    get_frontend_url,
    is_production,
    validate_production_configuration,
)
from app.main import create_app
from app.worker import main as worker_main


def production_environment() -> dict[str, str]:
    return {
        "APP_ENV": "production",
        "DATABASE_URL": "postgresql://user:private-password@pooler.example:5432/postgres?sslmode=require",
        "SUPABASE_URL": "https://project.supabase.co",
        "GEMINI_API_KEY": "private-gemini-key",
        "GOOGLE_CLIENT_ID": "test-client.apps.googleusercontent.com",
        "GOOGLE_CLIENT_SECRET": "private-google-secret",
        "TOKEN_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "GOOGLE_REDIRECT_URI": "https://api.example/gmail/callback",
        "FRONTEND_URL": "https://frontend.example/",
    }


class ProductionConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.environment = production_environment()

    def test_development_requires_no_new_configuration(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(is_production())
            self.assertEqual(get_frontend_url(), "http://localhost:3000")
            validate_production_configuration("api")
            validate_production_configuration("worker")

    def test_valid_production_api_configuration(self):
        with patch.dict(os.environ, self.environment, clear=True):
            validate_production_configuration("api")
            self.assertEqual(get_frontend_url(), "https://frontend.example")

    def test_frontend_origin_is_canonicalized_for_browser_cors(self):
        environment = self.environment | {"FRONTEND_URL": "https://FRONTEND.example:443/"}
        with patch.dict(os.environ, environment, clear=True):
            self.assertEqual(get_frontend_url(), "https://frontend.example")

    def test_worker_does_not_require_api_only_variables(self):
        environment = self.environment.copy()
        for name in ("SUPABASE_URL", "GEMINI_API_KEY", "GOOGLE_REDIRECT_URI", "FRONTEND_URL"):
            del environment[name]
        with patch.dict(os.environ, environment, clear=True):
            validate_production_configuration("worker")

    def test_every_required_api_variable_is_validated(self):
        for name in self.environment:
            if name == "APP_ENV":
                continue
            with self.subTest(name=name):
                environment = self.environment | {name: "   "}
                with patch.dict(os.environ, environment, clear=True):
                    with self.assertRaisesRegex(ConfigurationError, name):
                        validate_production_configuration("api")

    def test_unknown_environment_cannot_disable_production_checks(self):
        with patch.dict(os.environ, {"APP_ENV": "prod-secret"}, clear=True):
            with self.assertRaises(ConfigurationError) as caught:
                validate_production_configuration("api")
            self.assertNotIn("prod-secret", str(caught.exception))

    def test_invalid_frontend_origins_are_rejected_without_values(self):
        values = [
            "http://frontend.example", "https://localhost", "http://127.0.0.1:3000",
            "*", "https://*", "https://user:private-password@frontend.example",
            "https://frontend.example/path", "https://frontend.example?secret=token",
            "https://frontend.example#secret", "https://frontend.example:bad-port",
            "https://frontend.example?", "https://frontend.example#",
            "https://frontend.example\\evil", "https://front end.example",
        ]
        for value in values:
            with self.subTest(value=value):
                with patch.dict(os.environ, self.environment | {"FRONTEND_URL": value}, clear=True):
                    with self.assertRaises(ConfigurationError) as caught:
                        get_frontend_url()
                    self.assertNotIn(value, str(caught.exception))

    def test_production_callback_requires_https_and_exact_path(self):
        for value in ("http://api.example/gmail/callback", "https://api.example/wrong", "https://api.example/gmail/callback/", "https://api.example/gmail/callback?code=secret"):
            with self.subTest(value=value):
                with patch.dict(os.environ, self.environment | {"GOOGLE_REDIRECT_URI": value}, clear=True):
                    with self.assertRaisesRegex(ConfigurationError, "GOOGLE_REDIRECT_URI"):
                        validate_production_configuration("api")

    def test_production_supabase_origin_is_validated(self):
        with patch.dict(os.environ, self.environment | {"SUPABASE_URL": "https://private:secret@project.supabase.co"}, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "SUPABASE_URL"):
                validate_production_configuration("api")

    def test_database_ssl_is_required_without_modifying_url(self):
        for mode in ("disable", "allow", "prefer", ""):
            database_url = "postgresql://user:private-password@pooler.example/postgres"
            if mode:
                database_url += f"?sslmode={mode}"
            with self.subTest(mode=mode):
                with patch.dict(os.environ, self.environment | {"DATABASE_URL": database_url}, clear=True):
                    with self.assertRaisesRegex(ConfigurationError, "require SSL"):
                        validate_production_configuration("api")
                    self.assertEqual(os.environ["DATABASE_URL"], database_url)

    def test_parser_errors_do_not_expose_credentials_in_traceback(self):
        for name, value in (
            ("DATABASE_URL", "postgresql://private-password@host/db?invalid-secret-option=value"),
            ("TOKEN_ENCRYPTION_KEY", "private-invalid-key"),
        ):
            with self.subTest(name=name):
                with patch.dict(os.environ, self.environment | {name: value}, clear=True):
                    try:
                        validate_production_configuration("api")
                    except ConfigurationError as exc:
                        rendered = "".join(traceback.format_exception(exc))
                    else:
                        self.fail("Invalid configuration was accepted")
                    self.assertNotIn("private-password", rendered)
                    self.assertNotIn("invalid-secret-option", rendered)
                    self.assertNotIn("private-invalid-key", rendered)


class ProductionApiTests(unittest.TestCase):
    def test_cors_allows_only_configured_origin_and_authenticated_headers(self):
        with patch.dict(os.environ, production_environment(), clear=True):
            with TestClient(create_app()) as client:
                for origin, allowed in (
                    ("https://frontend.example", True),
                    ("http://localhost:3000", False),
                    ("https://frontend.example.evil", False),
                ):
                    with self.subTest(origin=origin):
                        response = client.options("/ask", headers={
                            "Origin": origin,
                            "Access-Control-Request-Method": "POST",
                            "Access-Control-Request-Headers": "authorization,content-type",
                        })
                        self.assertEqual(response.status_code, 200 if allowed else 400)
                        self.assertEqual(response.headers.get("access-control-allow-origin"), origin if allowed else None)
                self.assertEqual(client.get("/health").json(), {"status": "ok"})
                self.assertEqual(client.post("/ask", json={"question": "test"}).status_code, 401)

    def test_local_cors_still_works(self):
        with patch.dict(os.environ, {}, clear=True):
            with TestClient(create_app()) as client:
                response = client.get("/health", headers={"Origin": "http://localhost:3000"})
                self.assertEqual(response.headers.get("access-control-allow-origin"), "http://localhost:3000")

    def test_missing_configuration_prevents_production_startup(self):
        environment = production_environment()
        del environment["GEMINI_API_KEY"]
        with patch.dict(os.environ, environment, clear=True):
            with self.assertRaisesRegex(ConfigurationError, "GEMINI_API_KEY"):
                with TestClient(create_app()):
                    self.fail("Startup should have failed")

    def test_runtime_configuration_error_returns_safe_503(self):
        with patch.dict(os.environ, {}, clear=True):
            with TestClient(create_app()) as client:
                with self.assertLogs("app.main", level="ERROR") as logs:
                    response = client.get("/db-health")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json(), {"detail": "Service configuration is unavailable"})
                self.assertNotIn("DATABASE_URL", response.text)
                self.assertIn("DATABASE_URL", "".join(logs.output))

    @patch("app.main.complete_gmail_connection")
    def test_callback_uses_same_configured_frontend_as_cors(self, complete_connection):
        with patch.dict(os.environ, production_environment(), clear=True):
            with TestClient(create_app()) as client:
                response = client.get("/gmail/callback?code=private-code&state=private-state", follow_redirects=False)
                self.assertEqual(response.headers["location"], "https://frontend.example/?gmail=connected")
                self.assertNotIn("private-", response.text)
                complete_connection.assert_called_once_with("private-code", "private-state")


class ProductionWorkerTests(unittest.TestCase):
    @patch("app.worker.load_dotenv")
    @patch("app.worker.run_worker_loop")
    @patch("app.worker.run_next_gmail_sync_job")
    def test_bad_configuration_exits_before_claiming_work(self, run_next, run_loop, load_environment):
        environment = production_environment() | {"TOKEN_ENCRYPTION_KEY": "private-invalid-key"}
        with patch.dict(os.environ, environment, clear=True):
            with self.assertLogs("app.worker", level="ERROR") as logs:
                self.assertEqual(worker_main(["--once"]), 1)
        run_next.assert_not_called()
        run_loop.assert_not_called()
        self.assertNotIn("private-invalid-key", "".join(logs.output))


if __name__ == "__main__":
    unittest.main()
