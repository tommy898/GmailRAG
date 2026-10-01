# [GmailRAG](https://gmailrag.vercel.app)

GmailRAG is a web application that lets a user sign in, authorize read-only Gmail access, and ask grounded questions about indexed email. The current application uses Gemini Flash 3.5 for generation.


### To use the website

I will have to add test user in order to access the web app.
Please contact tzzhao@cs.washington.edu

### Video Demo

[![GmailRAG Vid](https://youtu.be/groqkXFVnO0)](https://youtu.be/groqkXFVnO0)

### Tech Stack

Frontend: Next.js, React, TypeScript, Tailwind CSS
UI: shadcn/ui and Vercel AI Elements
Backend: Python, FastAPI
Database: Supabase PostgreSQL + pgvector
Authentication: Supabase Auth with Google sign-in
Gmail Access: Google OAuth and Gmail API
Embedding: all-MiniLM-L6-v2
Reranking: ms-marco-MiniLM-L-6-v2
Answer generation: Gemini API (Flash 3.5)
Hosting: Vercel, Cloud Run service, Cloud Run Job for worker
Build and secrets: Cloud Build, Artifact Registry, Secret Manager

### Architecture

The frontend runs on Vercel and talks to a FastAPI backend deployed on Cloud Run. Supabase handles Auth and stores account, synchronization jobs, emails, chunks, and embeddings.

For syncrhonization, Email Sync runs separately as a job on Cloud Run. Therefore, the webstie can respond to the user without waiting for email processing.

### RAG(Retreieval-Augmented Generation)

For each question:

1. MiniLM generates a query embedding.
2. PostgreSQL retrieves up to 20 candidate chunks from the user's inbox using pgvector L2 distance.
3. The cross-encoder reranks the candidates and chooses up to 5 candidates (topk = 5 at max).
4. Gemini receives the question AND selected, ranked email chunks.
5. The frontend displays the generated answer alongside source metadata and previews from the selected chunks.


