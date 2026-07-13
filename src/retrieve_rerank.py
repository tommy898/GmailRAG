import chromadb
from sentence_transformers import CrossEncoder


CHROMA_PATH = "data/chroma"
COLLECTION_NAME = "email_chunks"
RETRIEVAL_COUNT = 20
TOP_K = 5
RERANKER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")


def retrieve_and_rerank(query, retrieval_count=RETRIEVAL_COUNT, top_k=TOP_K):
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    collection = client.get_collection(COLLECTION_NAME)

    results = collection.query(
        query_texts=[query],
        n_results=retrieval_count,
    )

    ids = results["ids"][0]
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    distances = results["distances"][0]

    pairs = []

    for document in documents:
        pairs.append((query, document))

    scores = RERANKER.predict(pairs)

    candidates = []

    for i, chunk_id in enumerate(ids):
        candidates.append(
            {
                "chunk_id": chunk_id,
                "document": documents[i],
                "metadata": metadatas[i],
                "distance": distances[i],
                "score": scores[i],
            }
        )

    candidates.sort(key=lambda candidate: candidate["score"], reverse=True)
    return candidates[:top_k]
