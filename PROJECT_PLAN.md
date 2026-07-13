# GmailRAG Project Plan

## Current State

GmailRAG currently has a working local retrieval pipeline:

1. Fetch Gmail messages into SQLite.
2. Normalize email fields into the `emails` table.
3. Chunk emails into the `email_chunks` table.
4. Embed chunks into local ChromaDB.
5. Retrieve candidate chunks with Chroma.
6. Rerank retrieved chunks with a local cross-encoder.

The local demo is one major step away from the full RAG loop: generation.

## Phase 1: Finish The Local Demo

Goal: make the terminal demo answer questions using retrieved email context.

### 1. Add Answer Generation

Create a local demo script that:

1. Accepts a question from the terminal.
2. Retrieves top candidate chunks from Chroma.
3. Reranks candidates.
4. Selects the top reranked chunks.
5. Builds an LLM prompt from those chunks.
6. Generates a grounded answer.
7. Prints the answer and source email metadata.

Recommended file:

```text
src/ask.py
```

The output should look like:

```text
Answer:
Your UW A&O appointment appears to be ...

Sources:
1. Subject: ...
   From: ...
   Date: ...
   Chunk ID: ...
```

### 2. Decide Generation Model

For the demo, use an API model unless privacy requirements block it.

Important privacy boundary:

```text
Only the top reranked chunks are sent to the model.
The full inbox is not sent.
```

The prompt should instruct the model to:

```text
Answer only using the provided email context.
Say when the answer is not present in the context.
Cite source numbers.
```

### 3. Clean The Local Scripts

Refactor enough to avoid duplicated logic:

```text
retrieve_and_rerank(question) -> candidates
build_context(candidates) -> prompt context
generate_answer(question, candidates) -> answer
```

Possible files:

```text
src/retrieve_rerank.py
src/ask.py
```

Do not over-refactor before generation works.

### 4. Add Demo Documentation

Update `README.md` with:

```text
setup commands
ingest command
chunk command
embed command
ask command
privacy notes
current limitations
```

### 5. Local Demo Completion Criteria

The local demo is complete when:

```text
python src/ask.py
```

can answer real inbox questions with:

1. A direct answer.
2. Source email metadata.
3. No full-inbox exposure.
4. Clear fallback when context is insufficient.

## Phase 2: Convert Demo Into A Website

Goal: turn the proven local RAG engine into an internship-quality deployed web app.

### Recommended Platform Stack

| Layer | Platform | Purpose |
|---|---|---|
| Frontend | Vercel + Next.js | Website, custom domain, UI |
| Backend API | Render + FastAPI | Python API for sync, retrieval, reranking, generation |
| Database | Supabase Postgres + pgvector | Users, emails, chunks, embeddings, answers |
| Auth | Supabase Auth | User login/session management |
| Background jobs | Render Background Worker | Gmail sync, chunking, embedding |
| Job state | Postgres `sync_jobs` table | Simple v1 job queue/status tracking |
| Gmail integration | Google Cloud OAuth + Gmail API | Connect Gmail accounts |
| LLM | OpenAI API or equivalent | Answer generation |
| Source control | GitHub | Repo, deploy hooks, project history |

### Web App Architecture

```text
Browser
↓
Next.js frontend on Vercel
↓
FastAPI backend on Render
↓
Supabase Postgres + pgvector
↓
Render background worker
↓
Gmail API / LLM API
```

### Production Data Model

Core tables:

```text
users
gmail_accounts
emails
email_chunks
email_embeddings
sync_jobs
queries
answers
answer_sources
```

SQLite and Chroma are replaced by:

```text
SQLite emails table       -> Postgres emails
SQLite email_chunks table -> Postgres email_chunks
Chroma vectors            -> pgvector embeddings
```

### Backend Responsibilities

FastAPI should expose endpoints like:

```text
GET  /health
POST /gmail/connect
POST /gmail/sync
GET  /sync/status
POST /ask
GET  /answers/{answer_id}
```

The backend owns:

```text
Gmail OAuth
token storage
database writes
retrieval
reranking
LLM calls
source citation formatting
```

### Worker Responsibilities

The worker handles slow jobs:

```text
fetch Gmail messages
normalize emails
chunk email text
embed chunks
update sync status
retry failed jobs
```

For v1, use a Postgres `sync_jobs` table instead of Redis.

Redis can be added later if job volume or reliability requirements increase.

### Frontend Responsibilities

Next.js should provide:

```text
landing page
sign in / sign up
connect Gmail page
sync status page
ask inbox page
answer display
source email cards
settings / disconnect Gmail
```

The frontend should not directly access Gmail tokens, OpenAI keys, or database credentials.

## Phase 3: Internship-Quality Polish

Add features that make the project credible beyond a demo:

```text
source citations
sync progress/status
error states
empty states
loading states
basic tests
schema migrations
environment variable documentation
deployment README
privacy/security notes
```

Recommended final README sections:

```text
Project overview
Architecture diagram
Tech stack
Data pipeline
Local setup
Deployment setup
Security/privacy considerations
Demo screenshots
Future work
```

## Important Constraints

Gmail read access is sensitive. A public production app using Gmail message content may require Google OAuth verification and additional security review.

For internship/demo purposes, keep the app limited to:

```text
personal use
test users
clear privacy explanation
minimal Gmail scopes
no unnecessary email exposure
```

## Immediate Next Step

Implement local generation:

```text
retrieved + reranked chunks -> prompt context -> LLM answer -> source citations
```

After that works, begin the web migration.

