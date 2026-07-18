# GmailRAG Project Plan


GmailRAG has a working local RAG demo pipeline:


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

## Worker Role

The background worker is not primarily for OAuth.

OAuth should usually stay in normal API routes:

```text
redirect user to Google
receive OAuth callback
exchange code for tokens
store token metadata
```

The worker is for slow indexing jobs that should not block an HTTP request:

```text
fetch many Gmail messages
parse and clean email bodies
insert normalized email rows
chunk email text
embed thousands of chunks
store vectors in pgvector
mark sync jobs done or failed
```

The API route should create a `sync_jobs` row and return quickly. The worker should poll `sync_jobs`, process pending jobs, and update job status.

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

### Milestone 1: FastAPI Backend Skeleton

Goal: create a Python backend with health checks, database connectivity, and a stable API boundary.

Endpoints:

```text
GET  /health
POST /ask
GET  /db-health
```

Deliverables:

```text
FastAPI app
DATABASE_URL environment variable
Supabase Postgres connection
schemas.py for request/response models
rag.py production boundary
/ask route wired to the RAG boundary
```

Completion criteria:

```text
backend runs locally
GET /health returns ok
backend can connect to Supabase
POST /ask route exists
```

Status:

```text
complete locally
```

### Milestone 2: Production Data Pipeline

Goal: populate Supabase with real searchable email data.

This milestone uses the existing local SQLite demo data as the first bridge into production storage. Real Gmail OAuth sync comes later.

Build:

```text
backend/app/chunking.py
backend/app/embeddings.py
backend/app/ingestion.py
scripts/migrate_sqlite_to_supabase.py
```

Flow:

```text
local SQLite emails
↓
Supabase emails
↓
chunk text
↓
Supabase email_chunks
↓
embed chunks
↓
Supabase email_embeddings with pgvector
```

Completion criteria:

```text
existing local emails can be inserted into Supabase
chunks can be recreated with production chunking code
chunk embeddings are stored in email_embeddings
pgvector rows use 384-dimensional vectors
the migration can be rerun safely without duplicate records
```

### Milestone 3: Production Retrieval

Goal: make the backend retrieve relevant chunks from Supabase/pgvector.

Build:

```text
backend/app/retrieval.py
```

Flow:

```text
question
↓
embed question
↓
SQL vector search against email_embeddings
↓
join email_chunks and emails metadata
↓
return top candidate chunks
```

Completion criteria:

```text
retrieval function accepts a question string
retrieval function returns top candidate chunks from Supabase
results include chunk text, subject, sender, date, distance, and chunk_id
no local ChromaDB dependency remains in backend retrieval
```

### Milestone 4: Reranking

Goal: improve retrieval quality before sending context to the LLM.

Build:

```text
backend/app/reranking.py
```

Flow:

```text
top 20 pgvector candidates
↓
cross-encoder reranker
↓
top 5 final sources
```

Completion criteria:

```text
reranker accepts candidate chunks from retrieval
reranker returns sorted candidates with scores
top reranked sources match or improve local demo quality
```

### Milestone 5: Generation

Goal: make `/ask` return real grounded answers.

Build:

```text
backend/app/generation.py
```

Flow:

```text
question + top reranked sources
↓
Gemini Flash
↓
answer text
↓
AskResponse JSON
```

Completion criteria:

```text
POST /ask accepts a question
retrieves relevant chunks from Postgres/pgvector
reranks candidates
calls Gemini
returns answer + source metadata as JSON
```

### Milestone 6: Persistence

Goal: store user questions, generated answers, and source citations.

Use existing tables:

```text
queries
answers
answer_sources
```

Flow:

```text
POST /ask
↓
save query
↓
generate answer
↓
save answer
↓
save source links
↓
return response
```

Completion criteria:

```text
each question is stored
each answer is stored
source chunks are linked to the answer
answer history can be queried later
```

### Milestone 7: Google OAuth Authorization

Goal: let a real user connect a Gmail account through Google OAuth.

This milestone is about authorization only. It proves the app can ask Google for Gmail access, receive the OAuth callback, and store the account metadata needed for future sync jobs.

Build:

```text
Google Cloud web OAuth client
OAuth consent screen test-user setup
minimal Gmail readonly scope
OAuth callback route
gmail_accounts token storage
```

Endpoints:

```text
GET /gmail/connect
GET /gmail/callback
```

Completion criteria:

```text
user can start Google OAuth from the app
Google redirects back to the backend callback
backend stores the connected Gmail account
tokens are stored server-side only
frontend never sees Gmail tokens
```

### Milestone 8: Background Sync Worker

Goal: replace the one-time SQLite migration with real web Gmail sync and indexing.

This milestone uses the Gmail account created by Milestone 7. The worker is the part that loops over many emails and calls the shared production ingestion pipeline.

Build:

```text
backend/app/gmail_service.py
backend/app/worker.py or worker.py
POST /gmail/sync
GET  /sync/status
```

Use the Postgres `sync_jobs` table first. Redis is not required for v1.

API responsibilities:

```text
POST /gmail/sync creates a sync_jobs row
GET /sync/status reads job progress
normal API requests return quickly
```

Worker responsibilities:

```text
poll pending sync_jobs
load stored Gmail account credentials
fetch Gmail messages
normalize email records
call ingestion.py for each email
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
worker calls the shared ingestion functions
GET /sync/status reports progress
failed jobs store readable errors
```

### Milestone 9: Next.js Frontend

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
user can sign in
user can trigger Gmail sync
user can ask a question
answer and source cards render correctly
```

### Milestone 10: Deployment And Polish

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
