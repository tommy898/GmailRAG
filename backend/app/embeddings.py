from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

_model: SentenceTransformer | None = None


def get_embedding_model() -> SentenceTransformer:
    global _model

    if _model is None:
        _model = SentenceTransformer(EMBEDDING_MODEL)

    return _model


def embed_texts(texts: list[str], batch_size: int = 64) -> list[list[float]]:
    if not texts:
        return []

    embeddings = get_embedding_model().encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=False,
    )

    return [
        [float(value) for value in embedding]
        for embedding in embeddings.tolist()
    ]


def embed_text(text: str) -> list[float]:
    return embed_texts([text])[0]

