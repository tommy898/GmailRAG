import logging
import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from app.db import get_connection
from app.gmail_accounts import (
    GmailAccountNotFoundError,
    IncompleteGmailCredentialsError,
)
from app.gmail_service import (
    GmailApiError,
    GmailCredentialRefreshError,
    GmailMessageNormalizationError,
    InvalidGmailCredentialScopeError,
    iter_normalized_gmail_messages,
)
from app.indexing import index_email
from app.ingestion import upsert_email
from app.sync_jobs import (
    claim_next_gmail_sync_job,
    complete_gmail_sync_job,
    fail_gmail_sync_job,
)


logger = logging.getLogger(__name__)


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
) -> GmailSyncRunResult | None:
    job = claim_next_gmail_sync_job()

    if job is None:
        return None

    messages_processed = 0
    chunks_indexed = 0

    try:
        for email in iter_normalized_gmail_messages(
            job.gmail_account_id,
            max_messages=max_messages,
        ):
            processed = process_gmail_message(
                job.gmail_account_id,
                email,
            )
            messages_processed += 1
            chunks_indexed += processed.chunk_count
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

    complete_gmail_sync_job(job.job_id, job.gmail_account_id)
    return GmailSyncRunResult(
        job_id=job.job_id,
        status="done",
        messages_processed=messages_processed,
        chunks_indexed=chunks_indexed,
    )
