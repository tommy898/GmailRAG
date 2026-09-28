import uuid
from collections.abc import Mapping


def require_email_value(email: Mapping[str, object], key: str) -> str:
    value = email.get(key)

    if not value:
        raise ValueError(f"email record is missing {key}")

    return str(value)


def upsert_email(
    conn,
    gmail_account_id: uuid.UUID,
    email: Mapping[str, object],
) -> uuid.UUID:
    gmail_message_id = require_email_value(email, "gmail_message_id")

    with conn.cursor() as cursor:
        cursor.execute(
            """
            insert into emails (
                gmail_account_id,
                gmail_message_id,
                gmail_thread_id,
                from_email,
                to_email,
                subject,
                sent_at,
                gmail_date_raw,
                snippet,
                body_text
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (gmail_account_id, gmail_message_id) do update set
                gmail_thread_id = excluded.gmail_thread_id,
                from_email = excluded.from_email,
                to_email = excluded.to_email,
                subject = excluded.subject,
                sent_at = excluded.sent_at,
                gmail_date_raw = excluded.gmail_date_raw,
                snippet = excluded.snippet,
                body_text = excluded.body_text,
                updated_at = now()
            returning id
            """,
            (
                gmail_account_id,
                gmail_message_id,
                email.get("gmail_thread_id"),
                email.get("from_email"),
                email.get("to_email"),
                email.get("subject"),
                email.get("sent_at"),
                email.get("gmail_date_raw"),
                email.get("snippet"),
                email.get("body_text"),
            ),
        )

        return cursor.fetchone()[0]
