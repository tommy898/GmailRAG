import uuid
from datetime import datetime

from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str


class Source(BaseModel):
    chunk_id: str
    subject: str | None = None
    from_email: str | None = None
    date: str | None = None
    score: float | None = None
    preview: str


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]


class GmailConnectResponse(BaseModel):
    authorization_url: str


class GmailSyncResponse(BaseModel):
    job_id: uuid.UUID
    status: str
    created: bool


class GmailSyncJobStatus(BaseModel):
    job_id: uuid.UUID
    status: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    created_at: datetime


class GmailSyncStatusResponse(BaseModel):
    connected: bool
    sync_status: str | None = None
    last_synced_at: datetime | None = None
    job: GmailSyncJobStatus | None = None
