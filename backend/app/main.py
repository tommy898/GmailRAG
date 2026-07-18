from fastapi import FastAPI
from app.db import fetch_database_time
from app.schemas import AskResponse, AskRequest
from app.rag import answer_question

app = FastAPI(title ="GmailRAG API")

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
def ask(request: AskRequest):
    return answer_question(request.question)

