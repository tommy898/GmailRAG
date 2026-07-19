from app.schemas import AskResponse, Source
from app.retrieval import retrieve_chunks

def answer_question(question: str) -> AskResponse:
    candidates = retrieve_chunks(question)

    sources = []

    for candidate in candidates[:5]:
        sources.append(
            Source(
                chunk_id=candidate["chunk_id"],
                subject=candidate["subject"],
                from_email=candidate["from_email"],
                date=candidate["date"],
                score=None,
                preview=candidate["text"][:300],
            )
        )

    return AskResponse(
        answer="This is a placeholder answer.",
        sources=sources,
    )