# GmailRAG Project Plan

## Current State

GmailRAG has a working local RAG demo pipeline:

1. Fetch Gmail messages into SQLite.
2. Normalize email fields into the `emails` table.
3. Chunk emails into the `email_chunks` table.
4. Embed chunks into local ChromaDB.
5. Retrieve candidate chunks with Chroma.
6. Rerank retrieved chunks with a local cross-encoder.
7. Generate grounded answers with Gemini Flash using the top reranked chunks.
8. Print answers with source email metadata.

The local demo is functionally complete. It should now be treated as the reference implementation while the project moves into the web-product phase.

## Product Goal

Build an web app that lets a user connect Gmail, sync recent emails, and ask natural-language questions about their inbox.

The deployed product should demonstrate:

```text
Gmail OAuth
email ingestion
database schema design
background sync jobs
chunking
embeddings
vector search
reranking
LLM answer generation
source citations
full-stack deployment
```

The final user experience should be:

```text
User signs in
↓
User connects Gmail
↓
App syncs and indexes emails
↓
User asks a question
↓
App returns a grounded answer with source emails
```

## Platform Stack

| Layer | Platform | Purpose |
|---|---|---|
| Frontend | Vercel + Next.js | Website, custom domain, UI |
| Backend API | Render + FastAPI | Python API for sync, retrieval, reranking, generation |
| Database | Supabase Postgres + pgvector | Users, emails, chunks, embeddings, answers |
| Auth | Supabase Auth | User login/session management |
| Background jobs | Render Background Worker | Gmail sync, chunking, embedding |
| Job state | Postgres `sync_jobs` table | Simple v1 job queue/status tracking |
| Gmail integration | Google Cloud OAuth + Gmail API | Connect Gmail accounts |
| LLM | Gemini Flash or equivalent | Answer generation |
| Source control | GitHub | Repo, deploy hooks, project history |

Redis is not required for v1. Use Postgres job rows first. Add Redis later only if job volume or reliability requirements justify it.

## Target Architecture

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
Gmail API / Gemini API
```

The frontend should never directly access Gmail tokens, Gemini keys, database credentials, or raw backend secrets.

## Production Data Model

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

Migration from local demo:

```text
SQLite emails table       -> Postgres emails
SQLite email_chunks table -> Postgres email_chunks
Chroma collection         -> pgvector email_embeddings
terminal input/output     -> FastAPI endpoint + Next.js UI
```

## Build Order

### Milestone 1: Production Schema

Goal: define the Supabase Postgres schema before building screens.

Deliverables:

```text
schema.sql or migration files
pgvector enabled
tables for users/accounts/emails/chunks/embeddings/jobs/answers/sources
clear foreign keys
unique constraints for Gmail message IDs
indexes for account_id, email_id, chunk_id, sync status, vector search
```

Completion criteria:

```text
Supabase project exists
schema can be applied from scratch
tables match the local demo's data model
```

### Milestone 2: FastAPI Backend Skeleton

Goal: create a deployable Python backend with health checks and basic structure.

Endpoints:

```text
GET  /health
POST /ask
POST /gmail/connect
POST /gmail/sync
GET  /sync/status
GET  /answers/{answer_id}
```

Deliverables:

```text
FastAPI app
environment variable loading
database connection
basic request/response models
local dev command
Render deployment config
```

Completion criteria:

```text
backend runs locally
GET /health returns ok
backend can connect to Supabase
backend can be deployed to Render
```

### Milestone 3: Port The RAG Pipeline

Goal: move the proven local logic into backend modules.

Replace local storage:

```text
sqlite3 reads/writes -> Postgres queries
Chroma search        -> pgvector search
terminal ask.py      -> POST /ask
```

Backend modules:

```text
gmail_service.py
chunking.py
embeddings.py
retrieval.py
reranking.py
generation.py
sources.py
```

Completion criteria:

```text
POST /ask accepts a question
retrieves relevant chunks from Postgres/pgvector
reranks candidates
calls Gemini
returns answer + source metadata as JSON
```

### Milestone 4: Background Sync Worker

Goal: avoid doing slow Gmail sync and embedding work inside normal web requests.

Use a Postgres `sync_jobs` table first.

Worker responsibilities:

```text
poll pending sync_jobs
fetch Gmail messages
normalize email records
chunk email text
embed chunks
store vectors in pgvector
mark jobs done or failed
record error messages
```

Completion criteria:

```text
POST /gmail/sync creates a job
worker processes the job
GET /sync/status reports progress
failed jobs store readable errors
```

### Milestone 5: Next.js Frontend

Goal: build the user-facing website.

Pages:

```text
landing page
sign in / sign up
connect Gmail
sync status
ask inbox
answer detail
settings / disconnect Gmail
```

Core UI components:

```text
question input
answer panel
source email cards
sync status indicator
loading states
error states
empty states
```

Completion criteria:

```text
frontend deployed on Vercel
custom domain connected
user can sign in
user can trigger Gmail sync
user can ask a question
answer and source cards render correctly
```

### Milestone 6: Deployment And Polish

Goal: make the project credible as a complete internship portfolio project.

Deliverables:

```text
Vercel frontend deployment
Render backend deployment
Render worker deployment
Supabase database
Google OAuth configured
environment variables documented
README updated
architecture diagram
demo screenshots
privacy/security notes
```

Completion criteria:

```text
fresh user can visit the domain
sign in
connect Gmail
sync emails
ask a question
receive a grounded answer with sources
```

## V1 Scope

Include:

```text
single-user or limited test-user support
Gmail readonly sync
manual sync button
recent email indexing
question answering
source citations
sync status
basic account settings
```

Exclude for v1:

```text
billing
team accounts
admin dashboard
attachment indexing
mobile app
Redis
Kubernetes
multi-email-provider support
complex analytics
```

## Security And Privacy Constraints

Gmail read access is sensitive. A public production app using Gmail message content may require Google OAuth verification and additional security review.

For internship/demo purposes, keep the app limited to:

```text
personal use
test users
minimal Gmail scopes
clear privacy explanation
no unnecessary email exposure
server-side token handling
no secrets in frontend code
```

Secrets must stay in environment variables or managed platform secrets:

```text
GEMINI_API_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
SUPABASE_SERVICE_ROLE_KEY
DATABASE_URL
```

Never commit:

```text
.env
credentials.json
token.json
data/
.venv/
```

## Immediate Next Step

Start with the production database design.

Next concrete task:

```text
Draft the Supabase Postgres + pgvector schema.
```

Reason:

```text
The schema defines the backend contract.
The backend API depends on the schema.
The frontend depends on the backend API.
```

