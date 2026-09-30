import base64
import binascii
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any

from google.auth.credentials import TokenState
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from app.config import get_required_environment_variable
from app.gmail_accounts import (
    StoredGmailCredentials,
    get_stored_gmail_credentials,
    update_gmail_credentials_after_refresh,
)
from app.token_crypto import decrypt_token, encrypt_token


GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
EXCLUDED_GMAIL_LABEL_IDS = frozenset({"SPAM", "TRASH"})
INITIAL_GMAIL_SYNC_MAX_MESSAGES = 1000
GMAIL_MESSAGE_REQUEST_INTERVAL_SECONDS = 0.25
# A full mailbox import can run long enough to encounter Gmail's transient
# per-user rate limit. Give the Google client enough exponential-backoff
# attempts to wait through the throttle instead of failing the entire job.
GMAIL_API_NUM_RETRIES = 8


class GmailProfileError(Exception):
    pass


class InvalidGmailCredentialScopeError(Exception):
    pass


class GmailCredentialRefreshError(Exception):
    pass


class GmailApiError(Exception):
    pass


class GmailHistoryExpiredError(GmailApiError):
    pass


class GmailMessageNormalizationError(Exception):
    pass


@dataclass(frozen=True)
class GmailHistoryChanges:
    upsert_message_ids: tuple[str, ...]
    deleted_message_ids: tuple[str, ...]
    next_history_id: str


@dataclass(frozen=True)
class GmailSyncPlan:
    mode: str
    messages: Iterator[dict[str, object]]
    deleted_message_ids: tuple[str, ...]
    next_history_id: str | None


HTML_BLOCK_TAGS = {
    "address",
    "article",
    "blockquote",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "p",
    "section",
    "table",
    "tr",
}
HTML_IGNORED_TAGS = {"head", "noscript", "script", "style", "title"}


class GmailHtmlTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        normalized_tag = tag.lower()

        if normalized_tag in HTML_IGNORED_TAGS:
            self.ignored_depth += 1
            return

        if self.ignored_depth == 0 and (
            normalized_tag == "br" or normalized_tag in HTML_BLOCK_TAGS
        ):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()

        if normalized_tag in HTML_IGNORED_TAGS:
            self.ignored_depth = max(0, self.ignored_depth - 1)
            return

        if self.ignored_depth == 0 and normalized_tag in HTML_BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.ignored_depth == 0:
            self.parts.append(data)

    def text(self) -> str:
        return "".join(self.parts)


def normalize_token_expiry(expiry: datetime | None) -> datetime | None:
    if expiry is None:
        return None

    if expiry.tzinfo is None:
        return expiry.replace(tzinfo=UTC)

    return expiry.astimezone(UTC)


def google_credentials_expiry(expiry: datetime | None) -> datetime | None:
    normalized_expiry = normalize_token_expiry(expiry)

    if normalized_expiry is None:
        return None

    return normalized_expiry.replace(tzinfo=None)


def build_gmail_credentials(
    stored_credentials: StoredGmailCredentials,
) -> Credentials:
    scopes = stored_credentials.scope.split()

    if GMAIL_READONLY_SCOPE not in scopes:
        raise InvalidGmailCredentialScopeError(
            "Stored Gmail credentials do not include read-only access"
        )

    return Credentials(
        token=decrypt_token(stored_credentials.access_token_encrypted),
        refresh_token=decrypt_token(
            stored_credentials.refresh_token_encrypted
        ),
        token_uri=GOOGLE_TOKEN_URI,
        client_id=get_required_environment_variable("GOOGLE_CLIENT_ID"),
        client_secret=get_required_environment_variable(
            "GOOGLE_CLIENT_SECRET"
        ),
        scopes=scopes,
        expiry=google_credentials_expiry(
            stored_credentials.token_expires_at
        ),
    )


def get_authorized_gmail_credentials(
    gmail_account_id: uuid.UUID,
) -> Credentials:
    stored_credentials = get_stored_gmail_credentials(gmail_account_id)
    credentials = build_gmail_credentials(stored_credentials)
    needs_refresh = (
        stored_credentials.token_expires_at is None
        or credentials.token_state is not TokenState.FRESH
    )

    if not needs_refresh:
        return credentials

    previous_refresh_token = credentials.refresh_token

    try:
        credentials.refresh(Request())
    except GoogleAuthError as exc:
        raise GmailCredentialRefreshError(
            "Google Gmail credentials could not be refreshed"
        ) from exc

    if not credentials.token:
        raise GmailCredentialRefreshError(
            "Google did not return a refreshed access token"
        )

    refreshed_refresh_token = (
        encrypt_token(credentials.refresh_token)
        if credentials.refresh_token
        and credentials.refresh_token != previous_refresh_token
        else None
    )

    update_gmail_credentials_after_refresh(
        gmail_account_id=gmail_account_id,
        access_token_encrypted=encrypt_token(credentials.token),
        refresh_token_encrypted=refreshed_refresh_token,
        token_expires_at=normalize_token_expiry(credentials.expiry),
    )

    return credentials


def build_gmail_api_service(credentials: Credentials):
    return build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )


def iter_gmail_message_ids(
    service,
    *,
    query: str | None = None,
    max_messages: int | None = None,
    include_spam_trash: bool = False,
) -> Iterator[str]:
    if max_messages is not None and max_messages < 0:
        raise ValueError("max_messages cannot be negative")

    if max_messages == 0:
        return

    normalized_query = query.strip() if query else None
    yielded_count = 0
    page_token = None
    seen_page_tokens = set()

    while True:
        remaining = (
            None
            if max_messages is None
            else max_messages - yielded_count
        )
        page_size = 500 if remaining is None else min(500, remaining)
        request_parameters: dict[str, Any] = {
            "userId": "me",
            "maxResults": page_size,
            "includeSpamTrash": include_spam_trash,
        }

        if normalized_query:
            request_parameters["q"] = normalized_query

        if page_token:
            request_parameters["pageToken"] = page_token

        try:
            response = (
                service.users()
                .messages()
                .list(**request_parameters)
                .execute(num_retries=GMAIL_API_NUM_RETRIES)
            )
        except HttpError as exc:
            raise GmailApiError("Gmail message listing failed") from exc

        if not isinstance(response, dict):
            raise GmailApiError("Gmail returned an invalid list response")

        messages = response.get("messages", [])

        if not isinstance(messages, list):
            raise GmailApiError("Gmail returned an invalid message list")

        for message in messages:
            message_id = message.get("id") if isinstance(message, dict) else None

            if not message_id:
                raise GmailApiError("Gmail returned a message without an ID")

            yield str(message_id)
            yielded_count += 1

            if max_messages is not None and yielded_count >= max_messages:
                return

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            return

        next_page_token = str(next_page_token)

        if next_page_token in seen_page_tokens:
            raise GmailApiError("Gmail repeated a pagination token")

        seen_page_tokens.add(next_page_token)
        page_token = next_page_token


def get_gmail_message(service, message_id: str) -> dict[str, Any]:
    if not message_id:
        raise ValueError("message_id cannot be empty")

    try:
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="full",
            )
            .execute(num_retries=GMAIL_API_NUM_RETRIES)
        )
    except HttpError as exc:
        raise GmailApiError("Gmail message download failed") from exc

    if not isinstance(message, dict) or not message.get("id"):
        raise GmailApiError("Gmail returned an invalid message")

    return message


def get_current_gmail_history_id(service) -> str:
    try:
        profile = (
            service.users()
            .getProfile(userId="me")
            .execute(num_retries=GMAIL_API_NUM_RETRIES)
        )
    except HttpError as exc:
        raise GmailApiError("Gmail profile could not be loaded") from exc

    history_id = profile.get("historyId") if isinstance(profile, dict) else None

    if not history_id:
        raise GmailApiError("Gmail profile did not include a history ID")

    return str(history_id)


def get_history_message(change: object) -> dict[str, Any]:
    message = change.get("message") if isinstance(change, dict) else None

    if not isinstance(message, dict) or not message.get("id"):
        raise GmailApiError("Gmail history contained an invalid message")

    return message


def get_history_message_id(change: object) -> str:
    return str(get_history_message(change)["id"])


def get_history_change_label_ids(change: object) -> frozenset[str]:
    label_ids = change.get("labelIds", []) if isinstance(change, dict) else []

    if not isinstance(label_ids, list):
        raise GmailApiError("Gmail history contained invalid labels")

    return frozenset(str(label_id) for label_id in label_ids)


def get_history_message_label_ids(change: object) -> frozenset[str]:
    label_ids = get_history_message(change).get("labelIds", [])

    if not isinstance(label_ids, list):
        raise GmailApiError("Gmail history message contained invalid labels")

    return frozenset(str(label_id) for label_id in label_ids)


def list_gmail_history_changes(
    service,
    start_history_id: str,
) -> GmailHistoryChanges:
    normalized_history_id = str(start_history_id or "").strip()

    if not normalized_history_id:
        raise ValueError("start_history_id cannot be empty")

    message_actions: dict[str, str] = {}
    predelete_message_ids: dict[str, None] = {}
    next_history_id = None
    page_token = None
    seen_page_tokens = set()

    while True:
        request_parameters: dict[str, Any] = {
            "userId": "me",
            "startHistoryId": normalized_history_id,
            "maxResults": 500,
        }

        if page_token:
            request_parameters["pageToken"] = page_token

        try:
            response = (
                service.users()
                .history()
                .list(**request_parameters)
                .execute(num_retries=GMAIL_API_NUM_RETRIES)
            )
        except HttpError as exc:
            if getattr(exc.resp, "status", None) == 404:
                raise GmailHistoryExpiredError(
                    "Gmail history checkpoint is no longer available"
                ) from exc

            raise GmailApiError("Gmail history listing failed") from exc

        if not isinstance(response, dict):
            raise GmailApiError("Gmail returned an invalid history response")

        history_records = response.get("history", [])

        if not isinstance(history_records, list):
            raise GmailApiError("Gmail returned an invalid history list")

        for history_record in history_records:
            if not isinstance(history_record, dict):
                raise GmailApiError("Gmail returned an invalid history record")

            messages_added = history_record.get("messagesAdded", [])
            messages_deleted = history_record.get("messagesDeleted", [])
            labels_added = history_record.get("labelsAdded", [])
            labels_removed = history_record.get("labelsRemoved", [])

            if not isinstance(messages_added, list) or not isinstance(
                messages_deleted,
                list,
            ) or not isinstance(labels_added, list) or not isinstance(
                labels_removed,
                list,
            ):
                raise GmailApiError(
                    "Gmail returned invalid message history changes"
                )

            for change in messages_added:
                action = (
                    "delete"
                    if get_history_message_label_ids(change)
                    & EXCLUDED_GMAIL_LABEL_IDS
                    else "upsert"
                )
                message_actions[get_history_message_id(change)] = action

            for change in messages_deleted:
                message_actions[get_history_message_id(change)] = "delete"

            for change in labels_added:
                if (
                    get_history_change_label_ids(change)
                    & EXCLUDED_GMAIL_LABEL_IDS
                ):
                    message_actions[
                        get_history_message_id(change)
                    ] = "delete"

            for change in labels_removed:
                if (
                    get_history_change_label_ids(change)
                    & EXCLUDED_GMAIL_LABEL_IDS
                ):
                    message_id = get_history_message_id(change)
                    predelete_message_ids[message_id] = None
                    message_actions[message_id] = "upsert"

        response_history_id = response.get("historyId")

        if response_history_id:
            next_history_id = str(response_history_id)

        next_page_token = response.get("nextPageToken")

        if not next_page_token:
            break

        next_page_token = str(next_page_token)

        if next_page_token in seen_page_tokens:
            raise GmailApiError("Gmail repeated a history pagination token")

        seen_page_tokens.add(next_page_token)
        page_token = next_page_token

    if not next_history_id:
        raise GmailApiError("Gmail history response omitted its checkpoint")

    return GmailHistoryChanges(
        upsert_message_ids=tuple(
            message_id
            for message_id, action in message_actions.items()
            if action == "upsert"
        ),
        deleted_message_ids=tuple(
            dict.fromkeys(
                [
                    message_id
                    for message_id, action in message_actions.items()
                    if action == "delete"
                ]
                + list(predelete_message_ids)
            )
        ),
        next_history_id=next_history_id,
    )


def decode_gmail_body_data(data: str) -> str:
    if not isinstance(data, str) or not data:
        return ""

    padding = "=" * (-len(data) % 4)

    try:
        decoded = base64.b64decode(
            (data + padding).encode("ascii"),
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise GmailMessageNormalizationError(
            "Gmail message body is not valid base64url data"
        ) from exc

    return decoded.decode("utf-8", errors="replace")


def clean_email_text(text: str) -> str:
    text = text.replace("\u2007", " ")
    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")
    cleaned_lines = []
    blank_line_pending = False

    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()

        if line:
            if blank_line_pending and cleaned_lines:
                cleaned_lines.append("")

            cleaned_lines.append(line)
            blank_line_pending = False
        elif cleaned_lines:
            blank_line_pending = True

    return "\n".join(cleaned_lines)


def gmail_html_to_text(html: str) -> str:
    parser = GmailHtmlTextExtractor()
    parser.feed(html)
    parser.close()
    return clean_email_text(parser.text())


def collect_gmail_text_parts(
    payload: dict[str, Any],
    plain_text_parts: list[str],
    html_parts: list[str],
) -> None:
    if payload.get("filename"):
        return

    mime_type = str(payload.get("mimeType") or "").split(";", 1)[0].lower()
    body = payload.get("body") or {}

    if not isinstance(body, dict):
        raise GmailMessageNormalizationError("Gmail message body is invalid")

    body_data = body.get("data")

    if body_data:
        decoded_text = decode_gmail_body_data(body_data)

        if mime_type == "text/plain":
            cleaned_text = clean_email_text(decoded_text)

            if cleaned_text:
                plain_text_parts.append(cleaned_text)
        elif mime_type == "text/html":
            cleaned_html = gmail_html_to_text(decoded_text)

            if cleaned_html:
                html_parts.append(cleaned_html)

    parts = payload.get("parts") or []

    if not isinstance(parts, list):
        raise GmailMessageNormalizationError("Gmail MIME parts are invalid")

    for part in parts:
        if not isinstance(part, dict):
            raise GmailMessageNormalizationError("Gmail MIME part is invalid")

        collect_gmail_text_parts(part, plain_text_parts, html_parts)


def extract_gmail_body_text(payload: dict[str, Any]) -> str:
    plain_text_parts: list[str] = []
    html_parts: list[str] = []
    collect_gmail_text_parts(payload, plain_text_parts, html_parts)

    if plain_text_parts:
        return "\n\n".join(plain_text_parts)

    return "\n\n".join(html_parts)


def decode_gmail_header(value: object) -> str:
    if value is None:
        return ""

    raw_value = str(value).strip()

    if not raw_value:
        return ""

    try:
        return str(make_header(decode_header(raw_value))).strip()
    except (LookupError, UnicodeError):
        return raw_value


def get_gmail_headers(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers") or []

    if not isinstance(headers, list):
        raise GmailMessageNormalizationError("Gmail message headers are invalid")

    normalized_headers = {}

    for header in headers:
        if not isinstance(header, dict):
            raise GmailMessageNormalizationError("Gmail message header is invalid")

        name = str(header.get("name") or "").strip().lower()

        if name and name not in normalized_headers:
            normalized_headers[name] = decode_gmail_header(header.get("value"))

    return normalized_headers


def parse_gmail_sent_at(
    internal_date: object,
    gmail_date_raw: str,
) -> datetime | None:
    if internal_date is not None:
        try:
            milliseconds = int(str(internal_date))
            return datetime.fromtimestamp(milliseconds / 1000, tz=UTC)
        except (OverflowError, TypeError, ValueError):
            pass

    if gmail_date_raw:
        try:
            parsed_date = parsedate_to_datetime(gmail_date_raw)

            if parsed_date is None:
                return None

            if parsed_date.tzinfo is None:
                return parsed_date.replace(tzinfo=UTC)

            return parsed_date.astimezone(UTC)
        except (OverflowError, TypeError, ValueError):
            pass

    return None


def normalize_gmail_message(message: dict[str, Any]) -> dict[str, object]:
    message_id = str(message.get("id") or "").strip()

    if not message_id:
        raise GmailMessageNormalizationError("Gmail message is missing its ID")

    payload = message.get("payload") or {}

    if not isinstance(payload, dict):
        raise GmailMessageNormalizationError("Gmail message payload is invalid")

    headers = get_gmail_headers(payload)
    gmail_date_raw = headers.get("date", "")

    return {
        "gmail_message_id": message_id,
        "gmail_thread_id": str(message.get("threadId") or "").strip(),
        "from_email": headers.get("from", ""),
        "to_email": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "sent_at": parse_gmail_sent_at(
            message.get("internalDate"),
            gmail_date_raw,
        ),
        "gmail_date_raw": gmail_date_raw,
        "snippet": str(message.get("snippet") or "").strip(),
        "body_text": extract_gmail_body_text(payload),
    }


def iter_normalized_messages_by_id(
    service,
    message_ids: Iterator[str],
    *,
    request_interval_seconds: float = GMAIL_MESSAGE_REQUEST_INTERVAL_SECONDS,
) -> Iterator[dict[str, object]]:
    if request_interval_seconds < 0:
        raise ValueError("request_interval_seconds cannot be negative")

    last_request_started_at: float | None = None

    for message_id in message_ids:
        if last_request_started_at is not None:
            elapsed = time.monotonic() - last_request_started_at
            remaining_delay = request_interval_seconds - elapsed

            if remaining_delay > 0:
                time.sleep(remaining_delay)

        last_request_started_at = time.monotonic()
        message = get_gmail_message(service, message_id)
        label_ids = message.get("labelIds", [])

        if not isinstance(label_ids, list):
            raise GmailApiError("Gmail message contained invalid labels")

        if frozenset(str(label_id) for label_id in label_ids) & (
            EXCLUDED_GMAIL_LABEL_IDS
        ):
            continue

        yield normalize_gmail_message(message)


def prepare_full_gmail_sync(
    service,
    *,
    max_messages: int = INITIAL_GMAIL_SYNC_MAX_MESSAGES,
    advance_checkpoint: bool = True,
) -> GmailSyncPlan:
    checkpoint = get_current_gmail_history_id(service)
    message_ids = iter_gmail_message_ids(
        service,
        max_messages=max_messages,
    )

    return GmailSyncPlan(
        mode="full",
        messages=iter_normalized_messages_by_id(service, message_ids),
        deleted_message_ids=(),
        next_history_id=checkpoint if advance_checkpoint else None,
    )


def prepare_incremental_gmail_sync(
    service,
    start_history_id: str,
    *,
    max_messages: int | None = None,
) -> GmailSyncPlan:
    changes = list_gmail_history_changes(service, start_history_id)
    upsert_message_ids = changes.upsert_message_ids

    if max_messages is not None:
        if max_messages < 0:
            raise ValueError("max_messages cannot be negative")

        upsert_message_ids = upsert_message_ids[:max_messages]

    return GmailSyncPlan(
        mode="incremental",
        messages=iter_normalized_messages_by_id(
            service,
            iter(upsert_message_ids),
        ),
        deleted_message_ids=changes.deleted_message_ids,
        next_history_id=(
            changes.next_history_id if max_messages is None else None
        ),
    )


def prepare_gmail_sync(
    gmail_account_id: uuid.UUID,
    last_history_id: str | None,
    *,
    max_messages: int | None = None,
) -> GmailSyncPlan:
    credentials = get_authorized_gmail_credentials(gmail_account_id)
    service = build_gmail_api_service(credentials)

    if last_history_id:
        try:
            return prepare_incremental_gmail_sync(
                service,
                last_history_id,
                max_messages=max_messages,
            )
        except GmailHistoryExpiredError:
            pass

    if max_messages is None:
        return prepare_full_gmail_sync(
            service,
            max_messages=INITIAL_GMAIL_SYNC_MAX_MESSAGES,
            advance_checkpoint=True,
        )

    return prepare_full_gmail_sync(
        service,
        max_messages=max_messages,
        advance_checkpoint=False,
    )


def iter_gmail_messages(
    gmail_account_id: uuid.UUID,
    *,
    query: str | None = None,
    max_messages: int | None = None,
    include_spam_trash: bool = False,
) -> Iterator[dict[str, Any]]:
    credentials = get_authorized_gmail_credentials(gmail_account_id)
    service = build_gmail_api_service(credentials)

    for message_id in iter_gmail_message_ids(
        service,
        query=query,
        max_messages=max_messages,
        include_spam_trash=include_spam_trash,
    ):
        yield get_gmail_message(service, message_id)


def iter_normalized_gmail_messages(
    gmail_account_id: uuid.UUID,
    *,
    query: str | None = None,
    max_messages: int | None = None,
    include_spam_trash: bool = False,
) -> Iterator[dict[str, object]]:
    for message in iter_gmail_messages(
        gmail_account_id,
        query=query,
        max_messages=max_messages,
        include_spam_trash=include_spam_trash,
    ):
        yield normalize_gmail_message(message)


def get_gmail_address(credentials: Credentials) -> str:
    service = build_gmail_api_service(credentials)
    profile = (
        service.users()
        .getProfile(userId="me")
        .execute(num_retries=GMAIL_API_NUM_RETRIES)
    )
    gmail_address = profile.get("emailAddress")

    if not gmail_address:
        raise GmailProfileError("Gmail profile did not include an email address")

    return str(gmail_address).strip().lower()
