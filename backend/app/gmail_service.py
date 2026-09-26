from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class GmailProfileError(Exception):
    pass


def get_gmail_address(credentials: Credentials) -> str:
    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )
    profile = service.users().getProfile(userId="me").execute()
    gmail_address = profile.get("emailAddress")

    if not gmail_address:
        raise GmailProfileError("Gmail profile did not include an email address")

    return str(gmail_address).strip().lower()
