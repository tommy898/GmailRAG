# (unfinished) GmailRAG from scratch

Working to have a actual web app...



Current State (local):
1. Fetch emails from Gmail using the Gmail API (ingestion)
2. Store email records in SQLite. (ingestion)
3. Chunking
   - Start with one chunk per email.
   - If an email body is over 1,000 characters, split it into chunks under 1,000 characters with 150 characters of overlap. (all-MiniLM-L6-v2 token limit)
4. Create embeddings for each chunk with all-MiniLM-L6-v2.
5. Store vectors and chunk metadata in ChromaDB.
6. Retrieve 20 relevant chunks with squared L2 distance.
7. Rerank retrieved chunks and come up with 5 most relevant chunks.
8. Generate an answer by Gemini with the retrieved chunks


