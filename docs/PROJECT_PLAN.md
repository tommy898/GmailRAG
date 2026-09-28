# GmailRAG Project Plan (for AI Agent)


GmailRAG has a working local RAG demo pipeline:


The local demo is functionally complete. It should now be treated as the reference implementation while the project moves into the web-product phase.

## Product Goal

Build a web app that lets a user connect Gmail, sync recent emails, and ask natural-language questions about their inbox.

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
backend/app/indexing.py
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

Status:

```text
complete
1000 emails migrated
4861 chunks created
4861 embeddings stored
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

Status:

```text
complete
POST /ask retrieves real pgvector source chunks from Supabase
```

### Milestone 4: Reranking

Goal: improve retrieval quality before sending context to the LLM.

Build:

```text
backend/app/rerank.py
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

Status:

```text
complete
POST /ask returns reranked sources with cross-encoder scores
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

Status:

```text
complete
POST /ask verified end to end with Supabase retrieval, cross-encoder reranking, Gemini 3.5 Flash generation, inline source citations, and source metadata
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

Status:

```text
deferred / post-v1
The v1 /ask response already returns the generated answer and its sources without requiring database persistence. Revisit this milestone when answer history, auditing, analytics, sharing, or user feedback becomes part of the product.
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

Implementation status:

```text
7.1  Supabase Google Sign-In configured and verified
7.2  Minimal Next.js authentication shell complete
7.3  auth.users UUID synchronized with profiles.id
7.4  FastAPI Supabase JWT verification complete
7.5  /ask protected and retrieval filtered by authenticated profile
7.6  Separate Gmail Access web OAuth client configured
7.7  Gmail OAuth environment and Fernet token encryption complete
7.8  Authenticated GET /gmail/connect complete
7.9  GET /gmail/callback, PKCE, encrypted token upsert, and frontend feedback complete
7.10 JWT, OAuth, logging, token, and two-account isolation verification complete
7.11 Environment, callback, test-user, and security documentation complete
```

Status:

```text
complete locally
33 backend security/OAuth tests pass
frontend lint and production build pass
live two-account test confirmed profile isolation
reconnection preserved the original gmail_accounts row and all indexed data
```

### Milestone 8: Background Sync Worker

Goal: replace the one-time SQLite migration with real web Gmail sync and indexing.

This milestone uses the Gmail account created by Milestone 7. The worker loops over many emails and coordinates the separate ingestion and indexing layers.

Indexing flow boundary:

Keep each module focused on one stage:

```text
gmail_service.py fetches and normalizes Gmail messages
ingestion.py validates and stores normalized email rows
chunking.py performs pure text processing
embeddings.py performs pure vector generation
indexing.py stores chunks and embeddings and exposes index_email()
worker.py coordinates ingestion and indexing for each message
```

Retrieval, reranking, and generation remain separate query-time stages used by `/ask`; they are not part of ingestion or background indexing.

Progress:

```text
8.1 indexing boundary cleanup complete
ingestion.py now contains only normalized email validation and persistence
indexing.py owns chunk and embedding persistence
replace_email_chunks() replaces all old chunker versions for one email
embed_and_store_chunks() generates and persists vectors for stored chunks
index_email() is the shared high-level operation for the future worker
8.2 stored Gmail credential loading and refresh complete
fresh access tokens are reused and expired tokens refresh through Google
refreshed access tokens and rotated refresh tokens are encrypted before storage
8.3 paginated Gmail message listing and full-message download complete
Gmail pages use the API maximum of 500 IDs and support an optional sync cap
full messages stream through one reused Gmail service instead of loading a mailbox at once
live one-message smoke test confirmed the stored credentials and Gmail API path
8.4 Gmail MIME normalization complete
nested MIME parts are traversed, text/plain is preferred, and HTML is a safe text fallback
attachments are excluded and encoded headers are decoded
Gmail internalDate becomes a timezone-aware sent_at value with the Date header as fallback
live one-message smoke test confirmed the normalized record shape without printing message content
8.5 single-message processing complete
worker.process_gmail_message() stores and indexes one normalized message in one transaction
indexing or persistence failures leave the transaction context as an error so partial work is rolled back
8.6 authenticated Gmail sync enqueue complete
POST /gmail/sync resolves the connected account from the authenticated profile and returns 202 quickly
pending or running Gmail sync jobs are reused while a locked account row prevents duplicate concurrent jobs
unconnected profiles receive a sanitized 409 response and no Gmail or token data is returned
8.7 single-job worker execution complete
the oldest pending Gmail job is claimed with row locking and SKIP LOCKED for multi-worker safety
normalized messages stream through the shared single-message persistence and indexing transaction
successful jobs mark the account ready while failures store only bounded sanitized errors
88 backend tests pass across authentication, OAuth, indexing, Gmail processing, and sync job execution
```

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
call ingestion.upsert_email() for each email
call indexing.index_email() for the stored email
mark jobs done or failed
record error messages
```

Completion criteria:

```text
POST /gmail/sync creates a job
worker processes the job
worker uses the shared ingestion and indexing functions
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

Deployment CORS note:

```text
Keep FastAPI CORS enabled when the deployed frontend and backend use different origins.
Replace the local http://localhost:3000 allowlist entry with the exact production frontend URL.
Keep localhost origins for local development only; do not include them in the production allowlist.
Do not use a wildcard production origin for authenticated requests.
If production later uses a same-origin proxy, the browser-facing CORS middleware may be removed.
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

Private values must stay in environment variables or managed platform secrets:

```text
DATABASE_URL
GEMINI_API_KEY
GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET
TOKEN_ENCRYPTION_KEY
```

Backend configuration also includes the public project URL and exact OAuth origins:

```text
SUPABASE_URL
GOOGLE_REDIRECT_URI
FRONTEND_URL
```

The frontend may contain only public configuration:

```text
NEXT_PUBLIC_SUPABASE_URL
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY
NEXT_PUBLIC_API_URL
```

The publishable key identifies the Supabase project; it is not a database secret. Keep RLS enabled and do not expose database credentials or a service-role key to the frontend.

Never commit:

```text
.env
credentials.json
token.json
data/
.venv/
```
