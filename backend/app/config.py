"""Environment configuration with errors that never include supplied values."""

import os
import re
from typing import Literal
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from psycopg.conninfo import conninfo_to_dict


class ConfigurationError(RuntimeError):
    pass


ADMIN_DATABASE_ROLES = frozenset({"postgres", "supabase_admin", "service_role"})


def get_required_environment_variable(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"{name} environment variable is not set")
    return value


def is_production() -> bool:
    environment = os.environ.get("APP_ENV", "development")
    if environment not in {"development", "production"}:
        raise ConfigurationError("APP_ENV must be development or production")
    return environment == "production"


def get_sync_dispatch_mode() -> str:
    mode = os.environ.get(
        "GMAIL_SYNC_DISPATCH", "cloud_run" if is_production() else "local"
    )
    if mode not in {"local", "cloud_run"} or (is_production() and mode != "cloud_run"):
        raise ConfigurationError("GMAIL_SYNC_DISPATCH must be cloud_run in production, or local in development")
    return mode


def get_cloud_run_job_name() -> str:
    parts = []
    # CLOUD_RUN_JOB is reserved runtime metadata, not our dispatch target.
    for name in ("CLOUD_RUN_PROJECT", "CLOUD_RUN_REGION", "GMAIL_SYNC_JOB_NAME"):
        value = get_required_environment_variable(name)
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value):
            raise ConfigurationError(f"{name} must be a valid resource identifier")
        parts.append(value)
    return f"projects/{parts[0]}/locations/{parts[1]}/jobs/{parts[2]}"


def validate_web_url(name: str, value: str, *, origin_only: bool = False) -> str:
    production = is_production()
    try:
        url = urlsplit(value)
        # Accessing port also checks for malformed/non-numeric ports.
        port = url.port
        local = url.hostname in {"localhost", "127.0.0.1", "::1"}
        valid = (
            url.scheme in {"http", "https"}
            and bool(url.hostname)
            and "*" not in url.hostname
            and url.username is None
            and url.password is None
            and "?" not in value
            and "#" not in value
            and not any(character.isspace() for character in value)
            and "\\" not in value
            and (port is None or port > 0)
            and (url.scheme == "https" or (local and not production))
            and (not production or not local)
            and (not origin_only or url.path in {"", "/"})
        )
    except ValueError:
        valid = False

    if not valid:
        raise ConfigurationError(
            f"{name} must be a valid HTTPS URL (local HTTP is development-only)"
        ) from None
    if origin_only:
        host = url.hostname
        if ":" in host:
            host = f"[{host}]"
        default_port = 443 if url.scheme == "https" else 80
        authority = host if port in {None, default_port} else f"{host}:{port}"
        return f"{url.scheme}://{authority}"
    return value


def get_frontend_url() -> str:
    if is_production():
        value = get_required_environment_variable("FRONTEND_URL")
    else:
        value = os.environ.get("FRONTEND_URL", "http://localhost:3000").strip()
    return validate_web_url("FRONTEND_URL", value, origin_only=True)


def get_supabase_url() -> str:
    return validate_web_url(
        "SUPABASE_URL",
        get_required_environment_variable("SUPABASE_URL"),
        origin_only=True,
    )


def validate_production_configuration(role: Literal["api", "worker"]) -> None:
    """Fail before serving requests/claiming jobs; never contact external services."""
    if not is_production():
        return

    required = [
        "DATABASE_URL",
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "TOKEN_ENCRYPTION_KEY",
    ]
    if role == "api":
        required += [
            "SUPABASE_URL",
            "GEMINI_API_KEY",
            "GOOGLE_REDIRECT_URI",
            "FRONTEND_URL",
        ]
    for name in required:
        get_required_environment_variable(name)

    try:
        database = conninfo_to_dict(
            get_required_environment_variable("DATABASE_URL")
        )
    except Exception:
        raise ConfigurationError("DATABASE_URL is invalid") from None
    if not database.get("host") or not database.get("dbname"):
        raise ConfigurationError("DATABASE_URL must specify a host and database")
    # Supabase pooler usernames append .PROJECT_REF to the PostgreSQL role.
    database_role = database.get("user", "").split(".", 1)[0]
    if not database_role or (
        database_role in ADMIN_DATABASE_ROLES
        and not (
            database_role == "postgres"
            and os.environ.get("ALLOW_ADMIN_DATABASE_FOR_PRIVATE_DEMO") == "true"
        )
    ):
        raise ConfigurationError(
            "DATABASE_URL must use a dedicated non-admin runtime account in production"
        )
    if database.get("sslmode") not in {"require", "verify-ca", "verify-full"}:
        raise ConfigurationError(
            "DATABASE_URL must explicitly require SSL in production"
        )

    try:
        Fernet(get_required_environment_variable("TOKEN_ENCRYPTION_KEY").encode())
    except (TypeError, ValueError):
        raise ConfigurationError("TOKEN_ENCRYPTION_KEY is invalid") from None

    if role == "api":
        if get_sync_dispatch_mode() == "cloud_run":
            get_cloud_run_job_name()
        get_frontend_url()
        get_supabase_url()
        redirect = validate_web_url(
            "GOOGLE_REDIRECT_URI",
            get_required_environment_variable("GOOGLE_REDIRECT_URI"),
        )
        if urlsplit(redirect).path != "/gmail/callback":
            raise ConfigurationError("GOOGLE_REDIRECT_URI must use /gmail/callback")
