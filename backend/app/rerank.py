from sentence_transformers import CrossEncoder

RERANKING_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

_model: CrossEncoder | None = None #cache

def get_reranking_model() -> CrossEncoder:
    global _model

    if _model is None:
        _model = CrossEncoder(RERANKING_MODEL)

    return _model

def rerank_candidates(
        question: str,
        candidates: list[dict],
        top_k: int = 5,
) -> list[dict]:
    if not candidates:
        return []
    
    pairs = [
        (question, candidate["text"])
        for candidate in candidates
    ]

    scores = get_reranking_model().predict(pairs)

    reranked = []

    for candidate, score in zip(candidates, scores, strict=True):
        candidate_with_score = dict(candidate)
        candidate_with_score["score"] = float(score)
        reranked.append(candidate_with_score)

    reranked.sort(
        key=lambda candidate: candidate["score"],
        reverse=True,
    )

    return reranked[:top_k]

