import json
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from cryptography.fernet import InvalidToken
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from oauthlib.oauth2 import OAuth2Error
from requests.exceptions import RequestException

from app.config import get_frontend_url, get_required_environment_variable

from app.gmail_accounts import (
    get_profile_email,
    upsert_gmail_account_credentials,
)
from app.gmail_service import (
    GMAIL_READONLY_SCOPE,
    get_gmail_address,
    normalize_token_expiry,
)
from app.token_crypto import encrypt_token, get_token_cipher


GMAIL_OAUTH_STATE_TTL_SECONDS = 10 * 60
GMAIL_OAUTH_CODE_VERIFIER_BYTES = 64


@dataclass(frozen=True)
class GmailOAuthState:
    profile_id: uuid.UUID
    code_verifier: str


class InvalidGmailOAuthStateError(Exception):
    pass


class GmailOAuthExchangeError(Exception):
    pass


class MissingGmailScopeError(Exception):
    pass


class GmailAccountMismatchError(Exception):
    pass


def get_google_client_config() -> dict:
    redirect_uri = get_required_environment_variable("GOOGLE_REDIRECT_URI")

    return {
        "web": {
            "client_id": get_required_environment_variable("GOOGLE_CLIENT_ID"),
            "client_secret": get_required_environment_variable(
                "GOOGLE_CLIENT_SECRET"
            ),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [redirect_uri],
        }
    }


def create_gmail_oauth_state(
    profile_id: uuid.UUID,
    code_verifier: str,
) -> str:
    payload = json.dumps(
        {
            "purpose": "gmail_oauth",
            "profile_id": str(profile_id),
            "nonce": secrets.token_urlsafe(32),
            "code_verifier": code_verifier,
        },
        separators=(",", ":"),
    )

    return get_token_cipher().encrypt(payload.encode()).decode()


def parse_gmail_oauth_state(state: str) -> GmailOAuthState:
    try:
        payload_bytes = get_token_cipher().decrypt(
            state.encode(),
            ttl=GMAIL_OAUTH_STATE_TTL_SECONDS,
        )
        payload = json.loads(payload_bytes.decode())

        if payload.get("purpose") != "gmail_oauth":
            raise InvalidGmailOAuthStateError("OAuth state has the wrong purpose")

        if not payload.get("nonce"):
            raise InvalidGmailOAuthStateError("OAuth state is missing its nonce")

        code_verifier = payload.get("code_verifier")

        if not isinstance(code_verifier, str) or not 43 <= len(code_verifier) <= 128:
            raise InvalidGmailOAuthStateError(
                "OAuth state has an invalid PKCE code verifier"
            )

        return GmailOAuthState(
            profile_id=uuid.UUID(payload["profile_id"]),
            code_verifier=code_verifier,
        )

    except InvalidGmailOAuthStateError:
        raise
    except (InvalidToken, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise InvalidGmailOAuthStateError(
            "Gmail OAuth state is invalid or expired"
        ) from exc


def build_gmail_authorization_url(profile_id: uuid.UUID) -> str:
    code_verifier = secrets.token_urlsafe(GMAIL_OAUTH_CODE_VERIFIER_BYTES)
    state = create_gmail_oauth_state(profile_id, code_verifier)
    redirect_uri = get_required_environment_variable("GOOGLE_REDIRECT_URI")

    flow = Flow.from_client_config(
        get_google_client_config(),
        scopes=[GMAIL_READONLY_SCOPE],
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = redirect_uri

    authorization_url, returned_state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="false",
        prompt="consent",
    )

    if not secrets.compare_digest(returned_state, state):
        raise RuntimeError("Google OAuth state was not preserved")

    return authorization_url


def exchange_gmail_authorization_code(
    code: str,
    state: str,
    code_verifier: str,
) -> Credentials:
    flow = Flow.from_client_config(
        get_google_client_config(),
        scopes=[GMAIL_READONLY_SCOPE],
        state=state,
        code_verifier=code_verifier,
        autogenerate_code_verifier=False,
    )
    flow.redirect_uri = get_required_environment_variable("GOOGLE_REDIRECT_URI")

    try:
        flow.fetch_token(code=code)
    except (OAuth2Error, RequestException, ValueError) as exc:
        raise GmailOAuthExchangeError(
            "Google authorization code exchange failed"
        ) from exc

    return flow.credentials


def get_granted_scopes(credentials: Credentials) -> set[str]:
    scopes = credentials.granted_scopes

    if scopes is None:
        scopes = credentials.scopes or []

    return {str(scope) for scope in scopes}


def complete_gmail_connection(code: str, state: str) -> uuid.UUID:
    oauth_state = parse_gmail_oauth_state(state)
    profile_id = oauth_state.profile_id
    profile_email = get_profile_email(profile_id)
    credentials = exchange_gmail_authorization_code(
        code,
        state,
        oauth_state.code_verifier,
    )

    if not credentials.token:
        raise GmailOAuthExchangeError("Google did not return an access token")

    granted_scopes = get_granted_scopes(credentials)

    if GMAIL_READONLY_SCOPE not in granted_scopes:
        raise MissingGmailScopeError(
            "Google did not grant Gmail read-only access"
        )

    gmail_address = get_gmail_address(credentials)

    if gmail_address.casefold() != profile_email.casefold():
        raise GmailAccountMismatchError(
            "Connected Gmail address does not match the signed-in profile"
        )

    encrypted_access_token = encrypt_token(credentials.token)
    encrypted_refresh_token = (
        encrypt_token(credentials.refresh_token)
        if credentials.refresh_token
        else None
    )

    return upsert_gmail_account_credentials(
        profile_id=profile_id,
        gmail_address=gmail_address,
        access_token_encrypted=encrypted_access_token,
        refresh_token_encrypted=encrypted_refresh_token,
        token_expires_at=normalize_token_expiry(credentials.expiry),
        scope=" ".join(sorted(granted_scopes)),
    )
