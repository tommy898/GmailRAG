from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

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

print("From:", headers_dict.get("from", ""))
print("To:", headers_dict.get("to", ""))
print("Subject:", headers_dict.get("subject", ""))
print("Date:", headers_dict.get("date", ""))