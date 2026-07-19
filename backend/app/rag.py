from app.schemas import AskResponse, Source
from app.retrieval import retrieve_chunks
from app.rerank import rerank_candidates

def answer_question(question: str) -> AskResponse:
    candidates = retrieve_chunks(question)

    sources = []
    reranked_candidates=rerank_candidates(question, candidates)

    for candidate in reranked_candidates:
        sources.append(
            Source(
                chunk_id=candidate["chunk_id"],
                subject=candidate["subject"],
                from_email=candidate["from_email"],
                date=candidate["date"],
                score=candidate["score"],
                preview=candidate["text"][:300],
            )
        )

    return AskResponse(
        answer="This is a placeholder answer.",
        sources=sources,
    )