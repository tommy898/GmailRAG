from pydantic import BaseModel

class AskRequest(BaseModel):
    question: str

class Source(BaseModel):
    chunk_id: str
    subject: str | None=None
    from_email: str | None=None
    date: str | None=None
    score: float | None=None
    preview: str

class AskResponse(BaseModel):
    answer: str
    sources: list[Source]