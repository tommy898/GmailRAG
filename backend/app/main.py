import uuid
from typing import Annotated

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.auth import get_current_profile_id
from app.db import fetch_database_time
from app.rag import answer_question
from app.schemas import AskRequest, AskResponse

app = FastAPI(title ="GmailRAG API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["POST"],
    allow_headers=["Authorization","Content-Type"],
)

@app.get("/health")

def health():
    return {"status": "ok"}

@app.get("/db-health")
def db_health():
    database_time = fetch_database_time()

    return{
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
