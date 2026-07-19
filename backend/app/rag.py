from app.generation import generate_answer
from app.retrieval import retrieve_chunks
from app.rerank import rerank_candidates
from app.schemas import AskResponse, Source

# Rag.py only orchestrates retrieving, reranking, generating, and formatting sources.


def answer_question(question: str) -> AskResponse:
    candidates = retrieve_chunks(question)
    reranked_candidates = rerank_candidates(question, candidates)
    answer = generate_answer(question, reranked_candidates)

    sources = []

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
        answer=answer,
        sources=sources,
    )
