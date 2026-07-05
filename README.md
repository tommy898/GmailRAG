# GmailRAG

GmailRAG is a local Gmail-based RAG project built from scratch, one layer at a time.

The project has moved out of notebook-only exploration. The notebook in `notebooks/`
is now reference material; active project code lives in `src/`.

## Current Milestone: Data Preparation

The first real milestone is to prepare the Gmail data that future RAG steps will use.

Current target:

```text
Fetch the most recent 1,000 inbox emails
Extract readable email text
Store normalized email records in local SQLite
```

No embeddings, vector database, or answer generation happen in this step.

## Data Flow

```text
Gmail API
  -> recent inbox message IDs
  -> full Gmail messages
  -> headers + readable body text
  -> normalized email records
  -> SQLite database
```

SQLite database:

```text
data/gmailrag.sqlite3
```

The `emails` table stores:

```text
message_id
thread_id
history_id
internal_date
from_header
to_header
subject
date_header
snippet
body
```

## Run

From the project root:

```bash
PYTHONPATH=src .venv/bin/python -m gmailrag ingest
```

By default, this fetches the most recent 1,000 inbox emails.

Useful options:

```bash
PYTHONPATH=src .venv/bin/python -m gmailrag ingest --max-results 1000
PYTHONPATH=src .venv/bin/python -m gmailrag ingest --max-results all
PYTHONPATH=src .venv/bin/python -m gmailrag status
```




## Next Project Steps

After data preparation works reliably:

1. Chunk stored email records into retrieval-sized text chunks.
2. Create embeddings for chunks.
3. Store embeddings in ChromaDB
4. Retrieve relevant chunks for a question.
5. Generate answers using retrieved Gmail context.
