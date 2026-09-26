import uuid
from datetime import datetime

from app.db import get_connection


class ProfileNotFoundError(Exception):
    pass


class MissingRefreshTokenError(Exception):
    pass


def get_profile_email(profile_id: uuid.UUID) -> str:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select email
                from profiles
                where id = %s
                """,
                (profile_id,),
            )
            row = cursor.fetchone()

    if row is None:
        raise ProfileNotFoundError("Profile does not exist")

    return str(row[0]).strip()


def upsert_gmail_account_credentials(
    profile_id: uuid.UUID,
    gmail_address: str,
    access_token_encrypted: str,
    refresh_token_encrypted: str | None,
    token_expires_at: datetime | None,
    scope: str,
) -> uuid.UUID:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select refresh_token_encrypted
                from gmail_accounts
                where profile_id = %s
                  and gmail_address = %s
                for update
                """,
                (profile_id, gmail_address),
            )
            existing_row = cursor.fetchone()
            existing_refresh_token = (
                existing_row[0] if existing_row is not None else None
            )
            refresh_token_to_store = (
                refresh_token_encrypted or existing_refresh_token
            )

            if not refresh_token_to_store:
                raise MissingRefreshTokenError(
                    "Google did not return a refresh token"
                )

            cursor.execute(
                """
                insert into gmail_accounts (
                    profile_id,
                    gmail_address,
                    access_token_encrypted,
                    refresh_token_encrypted,
                    token_expires_at,
                    scope,
                    sync_status
                )
                values (%s, %s, %s, %s, %s, %s, 'not_synced')
                on conflict (profile_id, gmail_address) do update set
                    access_token_encrypted = excluded.access_token_encrypted,
                    refresh_token_encrypted = excluded.refresh_token_encrypted,
                    token_expires_at = excluded.token_expires_at,
                    scope = excluded.scope,
                    sync_status = 'not_synced',
                    updated_at = now()
                returning id
                """,
                (
                    profile_id,
                    gmail_address,
                    access_token_encrypted,
                    refresh_token_to_store,
                    token_expires_at,
                    scope,
                ),
            )

            return cursor.fetchone()[0]
