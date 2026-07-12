import chromadb
from sentence_transformers import CrossEncoder


CHROMA_PATH = "data/chroma"  
COLLECTION_NAME = "email_chunks"
RERANKER = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")

query = input("Ask a question about your inbox:").strip()

if query == "":
    print("Invalid. Please enter a question.")
    raise SystemExit


client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_collection(COLLECTION_NAME)
#Retreive 
results = collection.query(
    query_texts=[query],
    n_results=20,
)
#L2 distance(chroma's default distance metric)


print(f"Query: {query}")
print(f"Results found: {len(results['ids'][0])}")

#Rerank
ids = results["ids"][0]
documents = results["documents"][0]
metadatas = results["metadatas"][0]
distances = results["distances"][0]

pairs = []

for document in documents:
    pairs.append((query, document))

scores = RERANKER.predict(pairs)

candidates = []

for i, chunk_id in enumerate(ids):#get all results into candidates
    candidates.append(
        {
            "chunk_id": chunk_id,
            "document": documents[i],
            "metadata": metadatas[i],
            "distance": distances[i],
            "score": scores[i],
        }
    )

candidates.sort(key=lambda x: x["score"], reverse=True)#sort by scores

top_k = 5 #best 5
top_candidates = candidates[:top_k]

for candidate in top_candidates:
    print('-' * 40)
    print("Chunk ID:", candidate["chunk_id"])
    print("Chroma distance", candidate["distance"])
    print("Reranked score", candidate["score"])
    print("Subject:", candidate["metadata"]["subject"])
    print("From:", candidate["metadata"]["from_email"])
    print("Date:", candidate["metadata"]["date"])
    print("Preview", candidate["document"][:200], "...")
