# GmailRAG

GmailRAG is a web application that lets a user sign in, authorize read-only Gmail access, and ask grounded questions about indexed email. The current application uses Next.js, FastAPI, Supabase Auth/Postgres/pgvector, Google OAuth, and Gemini.

## Current Status

- Milestones 1–5 are complete: backend, Supabase ingestion, vector retrieval, reranking, and grounded generation.
- Milestone 6 (answer-history persistence) is deferred until after v1.
- Milestone 7 is complete locally: Supabase sign-in, backend JWT verification, protected retrieval, Gmail authorization, encrypted token storage, and account-isolation testing.
- Milestone 8 is next: background Gmail synchronization and indexing.
- The frontend is currently a minimal authentication and API-testing shell; the full product UI remains Milestone 9.

## Architecture

```text
Browser
  → Next.js frontend
  → FastAPI backend
  → Supabase Postgres + pgvector
  → Gmail API / Gemini API
```

The browser uses Supabase only for authentication. FastAPI verifies the Supabase JWT and uses its `sub` UUID as the profile identity. Database queries and Gmail credentials stay on the backend.

## Local Setup

### Backend

Create `backend/.env` from [`backend/.env.example`](backend/.env.example), install the Python dependencies, and run FastAPI from the `backend` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
uvicorn app.main:app --reload --env-file .env
```

`--reload` watches Python files. `--env-file .env` loads the backend environment when uvicorn starts. Stop and restart uvicorn after changing `.env`.

For IPv4-only local networks and Render, use the Supabase **Session pooler** connection string on port `5432` for `DATABASE_URL`. Supabase's direct database hostname uses IPv6 unless the IPv4 add-on is enabled.

### Frontend

Create `frontend/.env.local` from [`frontend/.env.example`](frontend/.env.example), then run:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

## Environment Variables

### Backend configuration

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Supabase Postgres connection used by FastAPI. Prefer the Session pooler on IPv4 networks. |
| `SUPABASE_URL` | Public Supabase project base URL used to locate the JWT issuer and JWKS endpoint. |
| `GEMINI_API_KEY` | Private Gemini API credential. |
| `GEMINI_MODEL` | Optional, non-secret generation-model override. |
| `GOOGLE_CLIENT_ID` | Public identifier from the dedicated **GmailRAG Gmail Access** web OAuth client. |
| `GOOGLE_CLIENT_SECRET` | Private secret paired with the Gmail Access client ID. |
| `GOOGLE_REDIRECT_URI` | Public, exact FastAPI Gmail callback URL. |
| `TOKEN_ENCRYPTION_KEY` | Private Fernet key used to encrypt stored Google access and refresh tokens. |
| `FRONTEND_URL` | Public, exact frontend origin used for sanitized callback redirects. |

The backend secrets are `DATABASE_URL`, `GEMINI_API_KEY`, `GOOGLE_CLIENT_SECRET`, and `TOKEN_ENCRYPTION_KEY`. The other backend values are configuration rather than credentials.

Generate a Fernet key once and keep it stable. Changing it makes existing encrypted Gmail credentials unreadable:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### Frontend: public configuration

| Variable | Purpose |
|---|---|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase project base URL used for browser/server authentication. |
| `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` | Supabase publishable key; safe to expose when database RLS is enforced. |
| `NEXT_PUBLIC_API_URL` | FastAPI base URL, such as `http://localhost:8000`. |

The frontend does not receive `DATABASE_URL`, Google client secrets, Gemini keys, Fernet keys, or Gmail tokens.

## Google OAuth Configuration

GmailRAG uses two separate Google web OAuth clients:

1. **GmailRAG Supabase Sign-In** authenticates a user to GmailRAG through Supabase.
2. **GmailRAG Gmail Access** authorizes FastAPI to read Gmail with only `https://www.googleapis.com/auth/gmail.readonly`.

Do not reuse a desktop `credentials.json` client for either web flow.

### Callback and redirect URLs

| Configuration | Local | Production |
|---|---|---|
| Google redirect for Supabase Sign-In | `https://PROJECT_REF.supabase.co/auth/v1/callback` | Same Supabase callback |
| Supabase allowed frontend redirect | `http://localhost:3000/auth/callback` | `https://YOUR_VERCEL_DOMAIN/auth/callback` |
| Google redirect for Gmail Access | `http://localhost:8000/gmail/callback` | `https://YOUR_RENDER_DOMAIN/gmail/callback` |
| Backend `GOOGLE_REDIRECT_URI` | `http://localhost:8000/gmail/callback` | Exact Render Gmail callback above |
| Backend `FRONTEND_URL` | `http://localhost:3000` | Exact Vercel origin |
| Frontend `NEXT_PUBLIC_API_URL` | `http://localhost:8000` | Exact Render origin |

Google redirect URIs must match exactly. When deploying, replace the local FastAPI CORS allowlist with the exact Vercel origin; do not use a wildcard for authenticated browser requests.

### Google test users

While the Google Auth Platform audience is in **Testing** mode, add every account that will authorize Gmail under **Google Auth Platform → Audience → Test users**. Basic Google sign-in may work without this entry, but the Gmail read-only authorization will be blocked for non-test users. Testing-mode authorizations normally expire after seven days.

## Security Model

- `/ask` and `/gmail/connect` require a valid Supabase bearer token.
- FastAPI validates the JWT signature, issuer, audience, expiry, role, and `sub` UUID through Supabase JWKS.
- Retrieval SQL always filters through `gmail_accounts.profile_id` using the authenticated UUID.
- `/gmail/callback` does not require a bearer token because Google cannot send one; a Fernet-encrypted, ten-minute state binds the callback to the initiating profile.
- The Gmail authorization flow uses PKCE and requests only `gmail.readonly`.
- Gmail access and refresh tokens are encrypted before the database transaction and are never returned to the frontend.
- Callback query strings are redacted from uvicorn access logs.
- V1 requires the authorized Gmail address to match the Supabase profile email.
- `.env`, `credentials.json`, `token.json`, local data, and virtual environments must never be committed.

## Verification

Run the backend security suite:

```bash
cd backend
../.venv/bin/python -m unittest discover -s tests -v
```

Run frontend checks:

```bash
cd frontend
npm run lint
npm run build
```

Milestone 7 completed with 33 backend tests and a live two-account isolation check:

- A user cannot connect a different Gmail address to their profile.
- A second authenticated user cannot retrieve the first user's indexed sources.
- Separate users receive separate `gmail_accounts` rows and encrypted credentials.
- Reconnecting the original account preserves its row and its 1,000 emails, 4,861 chunks, and 4,861 embeddings.

See [`docs/PROJECT_PLAN.md`](docs/PROJECT_PLAN.md) for the remaining milestones.
