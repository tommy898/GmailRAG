import uuid
from dataclasses import dataclass
from datetime import datetime

from app.db import get_connection


PUBLIC_SYNC_ERROR_MESSAGES = frozenset(
    {
        "Gmail authorization is unavailable; reconnect Gmail",
        "Gmail messages could not be downloaded",
        "A Gmail message could not be normalized",
        "Gmail messages could not be indexed",
        "Gmail sync failed",
    }
)


class GmailAccountNotConnectedError(Exception):
    pass


class SyncJobStateError(Exception):
    pass


@dataclass(frozen=True)
class EnqueuedGmailSyncJob:
    job_id: uuid.UUID
    status: str
    created: bool


@dataclass(frozen=True)
class ClaimedGmailSyncJob:
    job_id: uuid.UUID
    gmail_account_id: uuid.UUID


@dataclass(frozen=True)
class GmailSyncStatus:
    connected: bool
    sync_status: str | None
    last_synced_at: datetime | None
    job_id: uuid.UUID | None
    job_status: str | None
    job_started_at: datetime | None
    job_finished_at: datetime | None
    job_error_message: str | None
    job_created_at: datetime | None


def sanitize_sync_error_message(error_message: object) -> str:
    normalized_message = str(error_message or "").strip()

    if normalized_message in PUBLIC_SYNC_ERROR_MESSAGES:
        return normalized_message

    return "Gmail sync failed"


def enqueue_gmail_sync_job(profile_id: uuid.UUID) -> EnqueuedGmailSyncJob:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select ga.id
                from gmail_accounts ga
                join profiles p on p.id = ga.profile_id
                where ga.profile_id = %s
                  and lower(ga.gmail_address) = lower(p.email)
                  and ga.access_token_encrypted is not null
                  and ga.refresh_token_encrypted is not null
                order by ga.updated_at desc
                limit 1
                for update of ga
                """,
                (profile_id,),
            )
            account_row = cursor.fetchone()

            if account_row is None:
                raise GmailAccountNotConnectedError(
                    "A connected Gmail account is required"
                )

            gmail_account_id = account_row[0]
            cursor.execute(
                """
                select id, status
                from sync_jobs
                where gmail_account_id = %s
                  and job_type = 'gmail_sync'
                  and status in ('pending', 'running')
                order by created_at desc
                limit 1
                """,
                (gmail_account_id,),
            )
            existing_job = cursor.fetchone()

            if existing_job is not None:
                return EnqueuedGmailSyncJob(
                    job_id=existing_job[0],
                    status=str(existing_job[1]),
                    created=False,
                )

            cursor.execute(
                """
                insert into sync_jobs (
                    gmail_account_id,
                    job_type,
                    status
                )
                values (%s, 'gmail_sync', 'pending')
                returning id, status
                """,
                (gmail_account_id,),
            )
            created_job = cursor.fetchone()

    return EnqueuedGmailSyncJob(
        job_id=created_job[0],
        status=str(created_job[1]),
        created=True,
    )


def get_gmail_sync_status(profile_id: uuid.UUID) -> GmailSyncStatus:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select
                    (
                        ga.access_token_encrypted is not null
                        and ga.refresh_token_encrypted is not null
                    ) as connected,
                    ga.sync_status,
                    ga.last_synced_at,
                    job.id,
                    job.status,
                    job.started_at,
                    job.finished_at,
                    job.error_message,
                    job.created_at
                from gmail_accounts ga
                join profiles p on p.id = ga.profile_id
                left join lateral (
                    select
                        id,
                        status,
                        started_at,
                        finished_at,
                        error_message,
                        created_at
                    from sync_jobs
                    where gmail_account_id = ga.id
                      and job_type = 'gmail_sync'
                    order by created_at desc
                    limit 1
                ) as job on true
                where ga.profile_id = %s
                  and lower(ga.gmail_address) = lower(p.email)
                order by ga.updated_at desc
                limit 1
                """,
                (profile_id,),
            )
            row = cursor.fetchone()

    if row is None:
        return GmailSyncStatus(
            connected=False,
            sync_status=None,
            last_synced_at=None,
            job_id=None,
            job_status=None,
            job_started_at=None,
            job_finished_at=None,
            job_error_message=None,
            job_created_at=None,
        )

    return GmailSyncStatus(
        connected=bool(row[0]),
        sync_status=str(row[1]),
        last_synced_at=row[2],
        job_id=row[3],
        job_status=str(row[4]) if row[4] is not None else None,
        job_started_at=row[5],
        job_finished_at=row[6],
        job_error_message=(
            sanitize_sync_error_message(row[7])
            if row[7] is not None
            else None
        ),
        job_created_at=row[8],
    )


def claim_next_gmail_sync_job() -> ClaimedGmailSyncJob | None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                with next_job as (
                    select id
                    from sync_jobs
                    where job_type = 'gmail_sync'
                      and status = 'pending'
                    order by created_at
                    for update skip locked
                    limit 1
                )
                update sync_jobs as job
                set
                    status = 'running',
                    started_at = now(),
                    finished_at = null,
                    error_message = null,
                    updated_at = now()
                from next_job
                where job.id = next_job.id
                returning job.id, job.gmail_account_id
                """
            )
            claimed_job = cursor.fetchone()

            if claimed_job is None:
                return None

            job_id, gmail_account_id = claimed_job
            cursor.execute(
                """
                update gmail_accounts
                set
                    sync_status = 'syncing',
                    updated_at = now()
                where id = %s
                """,
                (gmail_account_id,),
            )

    return ClaimedGmailSyncJob(
        job_id=job_id,
        gmail_account_id=gmail_account_id,
    )


def complete_gmail_sync_job(
    job_id: uuid.UUID,
    gmail_account_id: uuid.UUID,
    last_history_id: str | None = None,
) -> None:
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update sync_jobs
                set
                    status = 'done',
                    finished_at = now(),
                    error_message = null,
                    updated_at = now()
                where id = %s
                  and gmail_account_id = %s
                  and job_type = 'gmail_sync'
                  and status = 'running'
                returning id
                """,
                (job_id, gmail_account_id),
            )

            if cursor.fetchone() is None:
                raise SyncJobStateError(
                    "Gmail sync job is not running"
                )

            cursor.execute(
                """
                update gmail_accounts
                set
                    sync_status = 'ready',
                    last_history_id = coalesce(%s, last_history_id),
                    last_synced_at = now(),
                    updated_at = now()
                where id = %s
                """,
                (last_history_id, gmail_account_id),
            )


def fail_gmail_sync_job(
    job_id: uuid.UUID,
    gmail_account_id: uuid.UUID,
    error_message: str,
) -> None:
    safe_error_message = sanitize_sync_error_message(error_message)

    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                update sync_jobs
                set
                    status = 'failed',
                    finished_at = now(),
                    error_message = %s,
                    updated_at = now()
                where id = %s
                  and gmail_account_id = %s
                  and job_type = 'gmail_sync'
                  and status = 'running'
                returning id
                """,
                (safe_error_message, job_id, gmail_account_id),
            )

            if cursor.fetchone() is None:
                raise SyncJobStateError(
                    "Gmail sync job is not running"
                )

            cursor.execute(
                """
                update gmail_accounts
                set
                    sync_status = 'failed',
                    updated_at = now()
                where id = %s
                """,
                (gmail_account_id,),
            )
