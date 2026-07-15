# GmailRAG Production Database Schema

## Purpose

This document defines the production database model for moving GmailRAG from a local SQLite/Chroma demo into a full-stack web app.

The local demo currently uses:

```text
SQLite emails table
SQLite email_chunks table
Chroma collection for vectors
```

The production web app will use:

```text
Supabase Postgres
pgvector for embeddings
```

The goal is to keep the proven local pipeline while replacing local-only storage with production tables.

## Design Principles

1. Keep original Gmail email data separate from derived RAG data.
2. Keep chunks separate from embeddings.
3. Track which embedding model produced each vector.
4. Store answers and sources so responses can be audited later.
5. Support background sync jobs without Redis for v1.
6. Keep user/account boundaries explicit.

## Table Overview

Core tables:

```text
profiles
gmail_accounts
emails
email_chunks
email_embeddings
sync_jobs
queries
answers
answer_sources
```

Why `profiles` instead of `users`:

Supabase Auth already has an internal auth table for users. Application-specific user data usually lives in a separate public table that references the Supabase auth user ID.

## Entity Relationships

```text
profiles
  ↓
gmail_accounts
  ↓
emails
  ↓
email_chunks
  ↓
email_embeddings

profiles
  ↓
queries
  ↓
answers
  ↓
answer_sources
  ↓
email_chunks

gmail_accounts
  ↓
sync_jobs
```

## Tables

## profiles

Stores application-level user profile data.

Supabase Auth stores the actual login identity. This table stores app-specific user fields.

Columns:

```text
id uuid primary key
email text not null
display_name text
created_at timestamptz not null
updated_at timestamptz not null
```

Notes:

```text
id should match Supabase auth.users.id
```

## gmail_accounts

Stores Gmail accounts connected by a user.

One app user may eventually connect more than one Gmail account, so this is separate from `profiles`.

Columns:

```text
id uuid primary key
profile_id uuid not null references profiles(id)
gmail_address text not null
google_account_id text
access_token_encrypted text
refresh_token_encrypted text
token_expires_at timestamptz
scope text
last_history_id text
last_synced_at timestamptz
sync_status text not null
created_at timestamptz not null
updated_at timestamptz not null
```

Important:

```text
OAuth tokens must be encrypted before storage.
Frontend must never receive access_token or refresh_token.
```

Recommended constraints:

```text
unique(profile_id, gmail_address)
```

Possible `sync_status` values:

```text
not_synced
syncing
ready
failed
```

## emails

Stores normalized Gmail messages.

This maps closely to the local SQLite `emails` table.

Columns:

```text
id uuid primary key
gmail_account_id uuid not null references gmail_accounts(id)
gmail_message_id text not null
gmail_thread_id text
from_email text
to_email text
subject text
sent_at timestamptz
gmail_date_raw text
snippet text
body_text text
created_at timestamptz not null
updated_at timestamptz not null
```

Recommended constraints:

```text
unique(gmail_account_id, gmail_message_id)
```

Why both `sent_at` and `gmail_date_raw`:

```text
sent_at is parsed for sorting/filtering.
gmail_date_raw preserves the original Gmail header value.
```

Local mapping:

```text
message_id -> gmail_message_id
thread_id  -> gmail_thread_id
from_email -> from_email
to_email   -> to_email
subject    -> subject
date       -> gmail_date_raw / sent_at
snippet    -> snippet
body       -> body_text
```

## email_chunks

Stores retrieval-sized chunks derived from emails.

This maps to the local SQLite `email_chunks` table.

Columns:

```text
id uuid primary key
email_id uuid not null references emails(id)
chunk_index integer not null
text text not null
character_count integer
token_count integer
chunker_version text not null
created_at timestamptz not null
```

Recommended constraints:

```text
unique(email_id, chunk_index, chunker_version)
```

Why `chunker_version`:

Chunking rules will change. For example:

```text
v1: 2000 chars / 300 overlap
v2: 700 chars / 150 overlap
```

Storing the version makes rebuilds auditable.

## email_embeddings

Stores vector embeddings for chunks.

This replaces the local Chroma collection.

Columns:

```text
id uuid primary key
chunk_id uuid not null references email_chunks(id)
embedding vector(...)
embedding_model text not null
embedding_dimension integer not null
created_at timestamptz not null
```

Recommended constraints:

```text
unique(chunk_id, embedding_model)
```

Important:

The vector dimension depends on the embedding model.

Current local Chroma default model:

```text
all-MiniLM-L6-v2
dimension: 384
```

If using the same model in production:

```sql
embedding vector(384)
```

If switching models later, this dimension may need to change.

## sync_jobs

Tracks background jobs for Gmail sync, chunking, and embedding.

For v1, this replaces Redis. A Render background worker can poll this table.

Columns:

```text
id uuid primary key
gmail_account_id uuid not null references gmail_accounts(id)
job_type text not null
status text not null
started_at timestamptz
finished_at timestamptz
error_message text
created_at timestamptz not null
updated_at timestamptz not null
```

Possible `job_type` values:

```text
gmail_sync
chunk_emails
embed_chunks
full_reindex
```

Possible `status` values:

```text
pending
running
done
failed
```

Worker behavior:

```text
1. Find oldest pending job.
2. Mark it running.
3. Execute job.
4. Mark done or failed.
5. Store error_message on failure.
```

## queries

Stores user questions.

Columns:

```text
id uuid primary key
profile_id uuid not null references profiles(id)
gmail_account_id uuid references gmail_accounts(id)
question text not null
created_at timestamptz not null
```

Why store queries:

```text
debugging
history
answer auditing
future UI conversation history
```

## answers

Stores generated answers.

Columns:

```text
id uuid primary key
query_id uuid not null references queries(id)
answer_text text not null
generation_model text not null
created_at timestamptz not null
```

Current local generation model:

```text
gemini-3.5-flash
```

## answer_sources

Stores which chunks supported each answer.

Columns:

```text
id uuid primary key
answer_id uuid not null references answers(id)
chunk_id uuid not null references email_chunks(id)
source_rank integer not null
retrieval_distance double precision
rerank_score double precision
created_at timestamptz not null
```

Purpose:

```text
show source cards in the UI
audit whether answers were grounded
debug retrieval/reranking quality
```

Recommended constraints:

```text
unique(answer_id, source_rank)
unique(answer_id, chunk_id)
```

## Indexes

Recommended normal indexes:

```text
gmail_accounts(profile_id)
emails(gmail_account_id)
emails(gmail_account_id, gmail_message_id)
emails(sent_at)
email_chunks(email_id)
email_embeddings(chunk_id)
sync_jobs(status, created_at)
queries(profile_id, created_at)
answers(query_id)
answer_sources(answer_id)
```

Recommended vector index:

```text
email_embeddings.embedding
```

The exact pgvector index type should be chosen during SQL migration design.

Likely options:

```text
hnsw
ivfflat
```

For v1, HNSW is usually a good default if Supabase supports it in the project setup.

## Local Demo To Production Mapping

| Local Demo | Production |
|---|---|
| `data/gmailrag.sqlite3` | Supabase Postgres |
| SQLite `emails` | Postgres `emails` |
| SQLite `email_chunks` | Postgres `email_chunks` |
| Chroma `email_chunks` collection | Postgres `email_embeddings` with pgvector |
| `src/ingest_1000_emails.py` | `gmail_service.py` + worker job |
| `src/chunk.py` | `chunking.py` + worker job |
| `src/embed.py` | `embeddings.py` + worker job |
| `src/retrieve_rerank.py` | `retrieval.py` + `reranking.py` |
| `src/ask.py` | FastAPI `POST /ask` endpoint |

## Open Questions

1. Should v1 support only one Gmail account per user or multiple accounts?
2. Should we store full email bodies in Postgres, or store only cleaned text needed for RAG?
3. Which embedding model should production use?
4. Should generation answers be stored permanently or only returned live?
5. How much email source text should the frontend display?
6. How will Gmail OAuth token encryption be implemented?
7. Should sync jobs run manually only in v1, or also on a schedule?

## Immediate Next Step

Review this schema design.

After approval, convert it into:

```text
supabase/schema.sql
```

or Supabase migration files.

