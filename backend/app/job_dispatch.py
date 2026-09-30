"""Acknowledge a hosted worker launch, never wait for mailbox processing."""

import uuid

import google.auth
from google.auth.transport.requests import AuthorizedSession

from app.config import get_cloud_run_job_name, get_sync_dispatch_mode


class SyncJobLaunchError(RuntimeError):
    pass


def launch_gmail_sync_job(job_id: uuid.UUID) -> None:
    if get_sync_dispatch_mode() == "local":
        return
    resource = get_cloud_run_job_name()
    try:
        credentials, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        # No POST retries: a timed-out request may already have been accepted.
        # Another user click can safely launch the same DB job again.
        with AuthorizedSession(
            credentials, max_refresh_attempts=0, refresh_timeout=10
        ) as session:
            response = session.post(
                f"https://run.googleapis.com/v2/{resource}:run",
                json={"overrides": {
                    "containerOverrides": [{"args": ["--job-id", str(job_id)]}],
                    "taskCount": 1,
                }},
                timeout=(5, 20),
                max_allowed_time=30,
                allow_redirects=False,
            )
            if response.status_code != 200:
                raise SyncJobLaunchError("Gmail sync worker could not be launched")
            operation = response.json()
            if (
                not isinstance(operation, dict)
                or not isinstance(operation.get("name"), str)
                or not operation["name"]
                or operation.get("error")
            ):
                raise SyncJobLaunchError("Gmail sync worker could not be launched")
    except Exception:
        # Provider bodies/errors can contain credentials; discard, do not chain.
        raise SyncJobLaunchError("Gmail sync worker could not be launched") from None
