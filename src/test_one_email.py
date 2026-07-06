from pathlib import Path
import sqlite3
import base64
from bs4 import BeautifulSoup#for html to text conversion
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

def decode_base64url(data):
    decoded_bytes = base64.urlsafe_b64decode(data + "===")
    return decoded_bytes.decode("utf-8", errors="replace")#decode body to utf-8 and replace any invalid characters with a replacement character

def html_to_text(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup.get_text(separator = "\n", strip = True) #html -> text

def collect_email_text_parts(payload, plain_text_parts, html_parts):
    mime_type = payload.get("mimeType")
    body_data = payload.get("body", {}).get("data")

    if body_data:
        decoded_text = decode_base64url(body_data)

        if mime_type == "text/plain":
            plain_text_parts.append(decoded_text)
        elif mime_type == "text/html":
            html_parts.append(decoded_text)
    for part in payload.get("parts", []):
        collect_email_text_parts(part, plain_text_parts, html_parts)


def extract_email_text(message):
    plain_text_parts = []
    html_parts = []

    collect_email_text_parts(
        message["payload"],
        plain_text_parts,
        html_parts
    )

    if plain_text_parts != []:
        return "\n".join(plain_text_parts)
    if html_parts != []:
        return html_to_text("\n".join(html_parts))
    return ""


SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

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

service = build("gmail", "v1", credentials=creds)

results = service.users().messages().list(
    userId="me",
    labelIds=["INBOX"],
    maxResults=1,
).execute()

messages = results.get("messages", [])
message_id = messages[0]["id"]

full_message = service.users().messages().get(
    userId="me",
    id=message_id,
    format="full",
).execute()

print(full_message.keys())
print("Message ID:", full_message["id"])
print("Thread ID:", full_message["threadId"])
print("Snippet:", full_message.get("snippet", ""))

payload = full_message.get("payload", {})
headers = payload.get("headers", [])

headers_dict = {}

for header in headers:
    name = header["name"].lower()
    value = header["value"]
    headers_dict[name] = value


body = extract_email_text(full_message)

email_record = {
    "message_id": full_message["id"],
    "thread_id": full_message["threadId"],
    "from_email": headers_dict.get("from", ""),
    "to_email": headers_dict.get("to", ""),
    "subject": headers_dict.get("subject", ""),
    "date": headers_dict.get("date", ""),
    "snippet": full_message.get("snippet", ""),
    "body": body,
}

connection = sqlite3.connect("data/gmailrag.sqlite3")
cursor = connection.cursor()

cursor.execute(
    """
    INSERT OR REPLACE INTO emails (
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

connection.commit()
connection.close()

print("Saved email to SQLite:", email_record["message_id"])
