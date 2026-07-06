import base64
import re
import sqlite3
from pathlib import Path
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
MAX_EMAILS = 1000#fetch the most recent 1000 emails from the inbox
DB_PATH = "data/gmailrag.sqlite3"#raw emails db


def decode_base64url(data):
    padding = "=" * (-len(data) % 4)
    decoded_bytes = base64.urlsafe_b64decode(data + padding)
    return decoded_bytes.decode("utf-8", errors="replace")


def clean_text(text):
    text = text.replace("\u2007", " ")
    text = text.replace("\xa0", " ")
    text = text.replace("\u200b", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return clean_text(soup.get_text(separator="\n", strip=True))


def collect_email_text_parts(payload, plain_text_parts, html_parts):
    mime_type = payload.get("mimeType")
    body_data = payload.get("body", {}).get("data")

    if body_data:
        decoded_text = decode_base64url(body_data)

        if mime_type == "text/plain":
            plain_text_parts.append(clean_text(decoded_text))
        elif mime_type == "text/html":
            html_parts.append(html_to_text(decoded_text))

    for part in payload.get("parts", []):
        collect_email_text_parts(part, plain_text_parts, html_parts)


def extract_email_text(message):
    plain_text_parts = []
    html_parts = []

    collect_email_text_parts(
        message.get("payload", {}),
        plain_text_parts,
        html_parts,
    )

    if plain_text_parts != []:
        return "\n\n".join(plain_text_parts)

    if html_parts != []:
        return "\n\n".join(html_parts)

    return ""


def build_gmail_service():
    project_root = Path.cwd()
    credentials_path = project_root / "credentials.json"
    token_path = project_root / "token.json"

    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def list_recent_message_ids(service, max_emails):
    message_ids = []
    page_token = None

    while len(message_ids) < max_emails:
        remaining = max_emails - len(message_ids)

        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=["INBOX"],
                maxResults=min(500, remaining),
                pageToken=page_token,
            )
            .execute()
        )

        for message in results.get("messages", []):
            message_ids.append(message["id"])

        page_token = results.get("nextPageToken")

        if not page_token:
            break

    return message_ids


def fetch_full_message(service, message_id):
    return (
        service.users()
        .messages()
        .get(
            userId="me",
            id=message_id,
            format="full",
        )
        .execute()
    )


def headers_to_dict(headers):
    headers_dict = {}

    for header in headers:
        name = header.get("name", "").lower()
        value = header.get("value", "")

        if name:
            headers_dict[name] = value

    return headers_dict


def build_email_record(full_message):
    payload = full_message.get("payload", {})
    headers = headers_to_dict(payload.get("headers", []))
    body = extract_email_text(full_message)

    return {
        "message_id": full_message.get("id", ""),
        "thread_id": full_message.get("threadId", ""),
        "from_email": headers.get("from", ""),
        "to_email": headers.get("to", ""),
        "subject": headers.get("subject", ""),
        "date": headers.get("date", ""),
        "snippet": full_message.get("snippet", ""),
        "body": body,
    }


def save_email(cursor, email_record):
    cursor.execute(
        """
        INSERT INTO emails (
            message_id,
            thread_id,
            from_email,
            to_email,
            subject,
            date,
            snippet,
            body
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(message_id) DO UPDATE SET
            thread_id = excluded.thread_id,
            from_email = excluded.from_email,
            to_email = excluded.to_email,
            subject = excluded.subject,
            date = excluded.date,
            snippet = excluded.snippet,
            body = excluded.body
        """,
        (
            email_record["message_id"],
            email_record["thread_id"],
            email_record["from_email"],
            email_record["to_email"],
            email_record["subject"],
            email_record["date"],
            email_record["snippet"],
            email_record["body"],
        ),
    )


def main():
    service = build_gmail_service()
    message_ids = list_recent_message_ids(service, MAX_EMAILS)

    print(f"Found {len(message_ids)} recent inbox messages.")

    saved_count = 0
    error_count = 0

    connection = sqlite3.connect(DB_PATH)
    cursor = connection.cursor()

    for index, message_id in enumerate(message_ids, start=1):
        try:
            full_message = fetch_full_message(service, message_id)
            email_record = build_email_record(full_message)
            save_email(cursor, email_record)
            saved_count += 1
        except Exception as error:
            error_count += 1
            print(f"Error on message {message_id}: {error}")

        if index % 50 == 0:
            connection.commit()
            print(f"Processed {index}/{len(message_ids)} emails.")#debug

    connection.commit()
    connection.close()

    print("Done.")
    print(f"Saved emails: {saved_count}")
    print(f"Errors: {error_count}")
    print(f"Database: {DB_PATH}")


if __name__ == "__main__":
    main()
