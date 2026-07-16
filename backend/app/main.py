from fastapi import FastAPI

app = FastAPI(title ="GmailRAG API")

@app.get("/health")

def health():
    return {"status": "ok"}