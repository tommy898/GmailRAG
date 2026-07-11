import chromadb


CHROMA_PATH = "data/chroma"  
COLLECTION_NAME = "email_chunks"

query = input("Ask a question about your inbox:").strip()

if query == "":
    print("Invalid. Please enter a question.")
    raise SystemExit


client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_collection(COLLECTION_NAME)

results = collection.query(
    query_texts=[query],
    n_results=20,
)
#20 most similar chunk(will filter out less relevant chunks later by reranking)
#L2 distance(chroma's default distance metric)


print(f"Query: {query}")
print(f"Results found: {len(results['ids'][0])}")

for i, chunk_id in enumerate(results['ids'][0]):
    metadata = results['metadatas'][0][i]
    distance = results['distances'][0][i]
    document = results['documents'][0][i]
    print("-" * 40)
    print("Chunk ID:", chunk_id)
    print("Distance:", distance)
    print("Subject:", metadata["subject"])
    print("From:", metadata["from_email"])
    print("Date:", metadata["date"])
    print("Preview:", document[:300])


