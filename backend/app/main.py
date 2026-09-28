import logging
import uuid
from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from app.auth import get_current_profile_id
from app.db import fetch_database_time
from app.gmail_accounts import (
    MissingRefreshTokenError,
    ProfileNotFoundError,
)
from app.gmail_oauth import (
    GmailAccountMismatchError,
    GmailOAuthExchangeError,
    InvalidGmailOAuthStateError,
    MissingGmailScopeError,
    build_gmail_authorization_url,
    complete_gmail_connection,
    get_frontend_url,
)
from app.gmail_service import GmailProfileError
from app.rag import answer_question
from app.schemas import (
    AskRequest,
    AskResponse,
    GmailConnectResponse,
    GmailSyncJobStatus,
    GmailSyncResponse,
    GmailSyncStatusResponse,
)
from app.sync_jobs import (
    GmailAccountNotConnectedError,
    enqueue_gmail_sync_job,
    get_gmail_sync_status,
)


logger = logging.getLogger(__name__)


class RedactOAuthCallbackQueryFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not isinstance(record.args, tuple) or len(record.args) < 3:
            return True

        request_target = str(record.args[2])

        if request_target.startswith("/gmail/callback?"):
            arguments = list(record.args)
            arguments[2] = "/gmail/callback?[redacted]"
            record.args = tuple(arguments)

        return True


logging.getLogger("uvicorn.access").addFilter(
    RedactOAuthCallbackQueryFilter()
)
app = FastAPI(title="GmailRAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/db-health")
def db_health():
    database_time = fetch_database_time()

    return {
        "status": "ok",
        "database_time": database_time.isoformat(),
    }


@app.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    profile_id: Annotated[
        uuid.UUID,
        Depends(get_current_profile_id),
    ],
):
    return answer_question(request.question, profile_id)


@app.get("/gmail/connect", response_model=GmailConnectResponse)
def connect_gmail(
    profile_id: Annotated[
        uuid.UUID,
        Depends(get_current_profile_id),
    ],
):
    return GmailConnectResponse(
        authorization_url=build_gmail_authorization_url(profile_id)
    )


@app.post(
    "/gmail/sync",
    response_model=GmailSyncResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_gmail_sync(
    profile_id: Annotated[
        uuid.UUID,
        Depends(get_current_profile_id),
    ],
):
    try:
        job = enqueue_gmail_sync_job(profile_id)
    except GmailAccountNotConnectedError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Connect Gmail before starting a sync",
        ) from exc

    return GmailSyncResponse(
        job_id=job.job_id,
        status=job.status,
        created=job.created,
    )


@app.get("/sync/status", response_model=GmailSyncStatusResponse)
def sync_status(
    profile_id: Annotated[
        uuid.UUID,
        Depends(get_current_profile_id),
    ],
):
    current_status = get_gmail_sync_status(profile_id)
    job = None

    if (
        current_status.job_id is not None
        and current_status.job_status is not None
        and current_status.job_created_at is not None
    ):
        job = GmailSyncJobStatus(
            job_id=current_status.job_id,
            status=current_status.job_status,
            started_at=current_status.job_started_at,
            finished_at=current_status.job_finished_at,
            error_message=current_status.job_error_message,
            created_at=current_status.job_created_at,
        )

    return GmailSyncStatusResponse(
        connected=current_status.connected,
        sync_status=current_status.sync_status,
        last_synced_at=current_status.last_synced_at,
        job=job,
    )


def redirect_to_frontend(**query_parameters: str) -> RedirectResponse:
    query = urlencode(query_parameters)
    return RedirectResponse(
        url=f"{get_frontend_url()}/?{query}",
        status_code=303,
    )


@app.get("/gmail/callback", response_class=RedirectResponse)
def gmail_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    if error is not None:
        if error == "access_denied":
            error_code = "access_denied"
        else:
            error_code = "connection_failed"

        return redirect_to_frontend(gmail_error=error_code)

    if not state:
        return redirect_to_frontend(gmail_error="invalid_state")

    if not code:
        return redirect_to_frontend(gmail_error="connection_failed")

    try:
        complete_gmail_connection(code, state)
    except InvalidGmailOAuthStateError:
        return redirect_to_frontend(gmail_error="invalid_state")
    except GmailAccountMismatchError:
        return redirect_to_frontend(gmail_error="account_mismatch")
    except MissingRefreshTokenError:
        return redirect_to_frontend(gmail_error="refresh_token_missing")
    except (
        GmailOAuthExchangeError,
        GmailProfileError,
        MissingGmailScopeError,
        ProfileNotFoundError,
    ) as exc:
        cause_name = (
            type(exc.__cause__).__name__
            if exc.__cause__ is not None
            else "none"
        )
        logger.warning(
            "Gmail OAuth callback failed at %s (cause: %s)",
            type(exc).__name__,
            cause_name,
        )
        return redirect_to_frontend(gmail_error="connection_failed")
    except Exception as exc:
        logger.error(
            "Unexpected Gmail OAuth callback failure at %s",
            type(exc).__name__,
        )
        return redirect_to_frontend(gmail_error="connection_failed")

    return redirect_to_frontend(gmail="connected")
