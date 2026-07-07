# GmailRAG Project Context

This file is a handoff note for future work sessions. It explains what the project is, what has already been built, and how to continue in the same learning style.

## Goal

GmailRAG is a from-scratch RAG system for answering questions about a personal Gmail inbox.

The intended pipeline is:

1. Fetch emails from Gmail using the Gmail API.
2. Store normalized email records in SQLite.
3. Split emails into retrieval-sized chunks.
4. Create embeddings for each chunk.
5. Store vectors and chunk metadata in ChromaDB.
6. Retrieve relevant chunks using cosine similarity.
7. Rerank retrieved chunks.
8. Generate an answer using the retrieved email context.

## Current State

Completed:

- Gmail OAuth works with read-only Gmail scope.
- The newest 1,000 inbox emails have been fetched locally.
- Extracted email records are stored in SQLite at `data/gmailrag.sqlite3`.
- The `emails` table contains 1,000 rows.
- Basic data quality checks were run:
  - 36 emails had empty bodies.
  - 2 emails had empty subjects.
  - Long emails exist, with the largest bodies around 40,000 characters.
- The `email_chunks` table exists.
- `src/chunk.py` creates chunks from the `emails` table using the project chunking rule.

Current chunking rule:

- Combine `subject`, `from_email`, `date`, and `body` into chunk text.
- If combined text is 2,000 characters or fewer, create one chunk.
- If combined text is over 2,000 characters, split into 2,000-character chunks with 300 characters of overlap.

## Important Files

- `README.md`: short public project overview and planned pipeline.
- `src/ingest_1000_emails.py`: fetches 1,000 recent Gmail inbox messages and stores normalized records in SQLite.
- `src/chunk.py`: reads emails from SQLite and writes retrieval chunks into `email_chunks`.
- `src/get_email.py`: learning/debug script for reading stored emails.
- `src/insert_email.py`: learning/debug script for inserting fake email records.

Private/local files that must not be committed:

- `credentials.json`
- `token.json`
- `data/`
- `.venv/`
- `notebooks/`

These are already covered by `.gitignore`.

## Database Shape

`emails` stores one row per extracted Gmail message:

```sql
message_id TEXT PRIMARY KEY
thread_id TEXT
from_email TEXT
to_email TEXT
subject TEXT
date TEXT
snippet TEXT
body TEXT
```

`email_chunks` stores retrieval-sized text chunks:

```sql
chunk_id TEXT PRIMARY KEY
message_id TEXT
thread_id TEXT
subject TEXT
from_email TEXT
date TEXT
chunk_index INTEGER
text TEXT
FOREIGN KEY (message_id) REFERENCES emails(message_id)
```

SQLite is the source-of-truth store for readable pipeline data. ChromaDB will be the vector search store later.

## Working Style

This is a learning project. The user wants to build and understand the project step by step.

Preferred collaboration style:

- Explain each concept before moving to the next layer.
- Do not jump ahead to multiple RAG stages at once.
- Do not run large actions unless the user explicitly asks.
- Keep changes small and tied to the current concept.
- The user makes the project; the assistant guides, explains, reviews, and writes code only when asked.
- Avoid printing private email bodies or sensitive values in terminal output.
- Before GitHub commits, check for privacy leaks.

## Next Step

The next major RAG stage is embeddings.

Before embeddings, verify chunk output:

```sql
SELECT COUNT(*) FROM email_chunks;
SELECT MAX(LENGTH(text)) FROM email_chunks;
SELECT COUNT(*)
FROM email_chunks
WHERE message_id NOT IN (SELECT message_id FROM emails);
```

Expected:

- `email_chunks` count should be greater than 1,000.
- max chunk length should be `<= 2000`.
- orphan chunk count should be `0`.

Then proceed to:

1. Install/configure embedding dependencies.
2. Choose an embedding model.
3. Embed chunks in batches.
4. Store vectors and metadata in ChromaDB.
