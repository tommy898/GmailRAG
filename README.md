# (unfinished) GmailRAG from scratch

1. Fetch emails from Gmail using the Gmail API
2. Store email records in SQLite.
3. Chunking
   - Start with one chunk per email.
   - If an email body is over 2,000 characters, split it into chunks under 2,000 characters with 300 characters of overlap.
4. Create embeddings for each chunk.
5. Store vectors and chunk metadata in ChromaDB.
6. Retrieve relevant chunks using cosine similarity.
7. Rerank retrieved chunks.
8. Generate an answer using the retrieved email context.


