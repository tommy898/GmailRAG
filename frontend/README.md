# GmailRAG Frontend

This directory contains the Next.js frontend for GmailRAG.

Create `.env.local` from [`.env.example`](.env.example), then run:

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

The frontend handles Supabase authentication and sends the user's Supabase access token to FastAPI. It does not receive database credentials, Google client secrets, Gemini keys, Fernet keys, or Gmail tokens.

See the [root README](../README.md) for complete local setup, OAuth callback configuration, environment variables, security notes, and verification commands.
