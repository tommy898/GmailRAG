import uuid
from dataclasses import dataclass

from app.db import get_connection


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
                    last_synced_at = now(),
                    updated_at = now()
                where id = %s
                """,
                (gmail_account_id,),
            )


def fail_gmail_sync_job(
    job_id: uuid.UUID,
    gmail_account_id: uuid.UUID,
    error_message: str,
) -> None:
    safe_error_message = error_message.strip()[:500] or "Gmail sync failed"

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
