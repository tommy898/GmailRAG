import sqlite3
import chromadb

DB_PATH = "data/gmailrag.sqlite3"  # SQLite DB path
CHROMA_PATH = "data/chroma"  # Chroma DB path
COLLECTION_NAME = "email_chunks"  # Chroma collection name

#access SQLite email chunks
connection = sqlite3.connect(DB_PATH)
connection.row_factory = sqlite3.Row
cursor = connection.cursor()

cursor.execute(
    """
    SELECT
        chunk_id,
        message_id,
        thread_id,
        subject,
        from_email,
        date,
        chunk_index,
        text
    FROM email_chunks
    """
)

rows = cursor.fetchall()

ids = []
documents = []
metadatas = []

for row in rows:
    ids.append(row["chunk_id"])
    documents.append(row["text"])
    metadatas.append(
        {
            "message_id": row["message_id"],
            "thread_id": row["thread_id"],
            "subject": row["subject"],
            "from_email": row["from_email"],
            "date": row["date"],
            "chunk_index": row["chunk_index"],
        }
    )
connection.close()

#ChromaDB
client = chromadb.PersistentClient(path=CHROMA_PATH)
collection = client.get_or_create_collection(COLLECTION_NAME)

#add chunks
collection.add(
    ids=ids,
    documents=documents,
    metadatas=metadatas
)

print(f"Rows loaded from SQLite: {len(rows)}")
print(f"Chunks added: {len(ids)}")
print(f"collection count: {collection.count()}")