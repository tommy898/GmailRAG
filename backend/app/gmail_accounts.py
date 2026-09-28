import uuid
from dataclasses import dataclass
from datetime import datetime

from app.db import get_connection


class ProfileNotFoundError(Exception):
    pass


class MissingRefreshTokenError(Exception):
    pass


class GmailAccountNotFoundError(Exception):
    pass


class IncompleteGmailCredentialsError(Exception):
    pass


@dataclass(frozen=True)
class StoredGmailCredentials:
    account_id: uuid.UUID
    profile_id: uuid.UUID
    gmail_address: str
    access_token_encrypted: str
    refresh_token_encrypted: str
    token_expires_at: datetime | None
    scope: str


def get_gmail_sync_checkpoint(
    gmail_account_id: uuid.UUID,
) -> str | None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select last_history_id
                from gmail_accounts
                where id = %s
                """,
                (gmail_account_id,),
            )
            row = cursor.fetchone()

    if row is None:
        raise GmailAccountNotFoundError("Gmail account does not exist")

    history_id = row[0]
    return str(history_id) if history_id is not None else None


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


def get_stored_gmail_credentials(
    gmail_account_id: uuid.UUID,
) -> StoredGmailCredentials:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select
                    id,
                    profile_id,
                    gmail_address,
                    access_token_encrypted,
                    refresh_token_encrypted,
                    token_expires_at,
                    scope
                from gmail_accounts
                where id = %s
                """,
                (gmail_account_id,),
            )
            row = cursor.fetchone()

    if row is None:
        raise GmailAccountNotFoundError("Gmail account does not exist")

    access_token_encrypted = row[3]
    refresh_token_encrypted = row[4]

    if not access_token_encrypted or not refresh_token_encrypted:
        raise IncompleteGmailCredentialsError(
            "Gmail account must be reconnected"
        )

    return StoredGmailCredentials(
        account_id=row[0],
        profile_id=row[1],
        gmail_address=str(row[2]).strip().lower(),
        access_token_encrypted=str(access_token_encrypted),
        refresh_token_encrypted=str(refresh_token_encrypted),
        token_expires_at=row[5],
        scope=str(row[6] or "").strip(),
    )


def update_gmail_credentials_after_refresh(
    gmail_account_id: uuid.UUID,
    access_token_encrypted: str,
    refresh_token_encrypted: str | None,
    token_expires_at: datetime | None,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update gmail_accounts
                set
                    access_token_encrypted = %s,
                    refresh_token_encrypted = coalesce(
                        %s,
                        refresh_token_encrypted
                    ),
                    token_expires_at = %s,
                    updated_at = now()
                where id = %s
                returning id
                """,
                (
                    access_token_encrypted,
                    refresh_token_encrypted,
                    token_expires_at,
                    gmail_account_id,
                ),
            )
            row = cursor.fetchone()

    if row is None:
        raise GmailAccountNotFoundError("Gmail account does not exist")


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
