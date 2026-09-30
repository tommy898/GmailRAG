import argparse
import logging
import os
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from dotenv import load_dotenv

from app.config import ConfigurationError, is_production, validate_production_configuration
from app.db import get_connection
from app.gmail_accounts import (
    GmailAccountNotFoundError,
    IncompleteGmailCredentialsError,
    get_gmail_sync_checkpoint,
)
from app.gmail_service import (
    GmailApiError,
    GmailCredentialRefreshError,
    GmailMessageNormalizationError,
    InvalidGmailCredentialScopeError,
    prepare_gmail_sync,
)
from app.indexing import index_email
from app.ingestion import (
    delete_email,
    delete_emails_missing_from_full_sync,
    upsert_email,
)
from app.sync_jobs import (
    claim_next_gmail_sync_job,
    claim_gmail_sync_job,
    complete_gmail_sync_job,
    fail_gmail_sync_job,
    recover_interrupted_gmail_sync_job,
)


logger = logging.getLogger(__name__)
SYNC_PROGRESS_LOG_INTERVAL = 100


@dataclass(frozen=True)
class ProcessedGmailMessage:
    email_id: uuid.UUID
    chunk_count: int


@dataclass(frozen=True)
class GmailSyncRunResult:
    job_id: uuid.UUID
    status: str
    messages_processed: int
    chunks_indexed: int


def delete_gmail_message(
    gmail_account_id: uuid.UUID,
    gmail_message_id: str,
) -> bool:
    with get_connection() as conn:
        return delete_email(conn, gmail_account_id, gmail_message_id)


def reconcile_full_gmail_sync(
    gmail_account_id: uuid.UUID,
    gmail_message_ids: list[str],
) -> int:
    with get_connection() as conn:
        return delete_emails_missing_from_full_sync(
            conn,
            gmail_account_id,
            gmail_message_ids,
        )


def process_gmail_message(
    gmail_account_id: uuid.UUID,
    email: Mapping[str, object],
    *,
    embed_chunks: bool = True,
) -> ProcessedGmailMessage:
    """Store and index one normalized Gmail message atomically."""
    with get_connection() as conn:
        email_id = upsert_email(conn, gmail_account_id, email)
        chunk_count = index_email(
            conn,
            email_id,
            email,
            embed_chunks=embed_chunks,
        )

    return ProcessedGmailMessage(
        email_id=email_id,
        chunk_count=chunk_count,
    )


def safe_gmail_sync_error_message(error: Exception) -> str:
    if isinstance(
        error,
        (
            GmailAccountNotFoundError,
            GmailCredentialRefreshError,
            IncompleteGmailCredentialsError,
            InvalidGmailCredentialScopeError,
        ),
    ):
        return "Gmail authorization is unavailable; reconnect Gmail"

    if isinstance(error, GmailApiError):
        return "Gmail messages could not be downloaded"

    if isinstance(error, GmailMessageNormalizationError):
        return "A Gmail message could not be normalized"

    return "Gmail messages could not be indexed"


def run_next_gmail_sync_job(
    *,
    max_messages: int | None = None,
    job_id: uuid.UUID | None = None,
) -> GmailSyncRunResult | None:
    job = claim_next_gmail_sync_job() if job_id is None else claim_gmail_sync_job(job_id)

    if job is None:
        return None

    messages_processed = 0
    chunks_indexed = 0
    processed_message_ids: list[str] = []

    try:
        last_history_id = get_gmail_sync_checkpoint(
            job.gmail_account_id,
        )
        sync_plan = prepare_gmail_sync(
            job.gmail_account_id,
            last_history_id,
            max_messages=max_messages,
        )

        for message_id in sync_plan.deleted_message_ids:
            delete_gmail_message(job.gmail_account_id, message_id)

        for email in sync_plan.messages:
            processed = process_gmail_message(
                job.gmail_account_id,
                email,
            )
            messages_processed += 1
            chunks_indexed += processed.chunk_count
            processed_message_ids.append(str(email["gmail_message_id"]))

            if messages_processed % SYNC_PROGRESS_LOG_INTERVAL == 0:
                logger.info(
                    "Gmail sync job %s progress messages=%s chunks=%s",
                    job.job_id,
                    messages_processed,
                    chunks_indexed,
                )

        if sync_plan.mode == "full" and max_messages is None:
            reconcile_full_gmail_sync(
                job.gmail_account_id,
                processed_message_ids,
            )
    except Exception as exc:
        error_message = safe_gmail_sync_error_message(exc)
        logger.error(
            "Gmail sync job %s failed at %s",
            job.job_id,
            type(exc).__name__,
        )
        fail_gmail_sync_job(
            job.job_id,
            job.gmail_account_id,
            error_message,
        )
        return GmailSyncRunResult(
            job_id=job.job_id,
            status="failed",
            messages_processed=messages_processed,
            chunks_indexed=chunks_indexed,
        )

    complete_gmail_sync_job(
        job.job_id,
        job.gmail_account_id,
        sync_plan.next_history_id,
    )
    return GmailSyncRunResult(
        job_id=job.job_id,
        status="done",
        messages_processed=messages_processed,
        chunks_indexed=chunks_indexed,
    )


def log_gmail_sync_result(result: GmailSyncRunResult) -> None:
    logger.info(
        "Gmail sync job %s finished with status=%s messages=%s chunks=%s",
        result.job_id,
        result.status,
        result.messages_processed,
        result.chunks_indexed,
    )


def run_worker_loop(poll_seconds: float) -> None:
    if poll_seconds <= 0:
        raise ValueError("poll_seconds must be positive")

    while True:
        result = run_next_gmail_sync_job()

        if result is None:
            time.sleep(poll_seconds)
        else:
            log_gmail_sync_result(result)


def worker_poll_seconds() -> float:
    raw_value = os.environ.get("WORKER_POLL_SECONDS", "5")

    try:
        poll_seconds = float(raw_value)
    except ValueError as exc:
        raise ValueError("WORKER_POLL_SECONDS must be a number") from exc

    if poll_seconds <= 0:
        raise ValueError("WORKER_POLL_SECONDS must be positive")

    return poll_seconds


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the Gmail sync worker")
    execution = parser.add_mutually_exclusive_group()
    execution.add_argument(
        "--once",
        action="store_true",
        help="Process at most one pending job and exit",
    )
    execution.add_argument("--job-id", type=uuid.UUID, help="Process only this pending job and exit")
    execution.add_argument("--recover-job", type=uuid.UUID, help="Mark an interrupted running job failed; does not sync")
    parser.add_argument("--confirm-worker-stopped", action="store_true", help="Confirm all executions for the recovery job have terminated")
    arguments = parser.parse_args(argv)
    if arguments.recover_job and not arguments.confirm_worker_stopped:
        parser.error("Recovery requires stopping all executions first and --confirm-worker-stopped")
    if arguments.confirm_worker_stopped and not arguments.recover_job:
        parser.error("--confirm-worker-stopped requires --recover-job")
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    try:
        validate_production_configuration("worker")
        if is_production() and not (arguments.job_id or arguments.recover_job):
            raise ConfigurationError("Hosted worker requires --job-id; polling and --once are development-only")
    except ConfigurationError as exc:
        logger.error("Worker configuration invalid: %s", exc)
        return 1

    try:
        if arguments.recover_job:
            recover_interrupted_gmail_sync_job(arguments.recover_job)
            logger.info("Interrupted Gmail sync job marked failed; retry from the website")
            return 0
        if arguments.once or arguments.job_id:
            result = (
                run_next_gmail_sync_job(job_id=arguments.job_id)
                if arguments.job_id else run_next_gmail_sync_job()
            )

            if result is None:
                logger.info("No claimable Gmail sync job; execution is a no-op")
                return 0

            log_gmail_sync_result(result)
            return 0 if result.status == "done" else 1

        run_worker_loop(worker_poll_seconds())
    except KeyboardInterrupt:
        logger.info("Gmail sync worker stopped")
        return 1 if arguments.job_id else 0
    except Exception as exc:
        logger.error("Gmail sync worker stopped at %s", type(exc).__name__)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
