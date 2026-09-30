-- GmailRAG's browser uses Supabase Auth only; application data goes through
-- authenticated FastAPI routes. Apply as postgres, not as a runtime identity.
-- No rows, encryption keys, table definitions, or RLS policies are changed.
begin;

revoke all privileges on table
    public.profiles,
    public.gmail_accounts,
    public.emails,
    public.email_chunks,
    public.email_embeddings,
    public.sync_jobs,
    public.queries,
    public.answers,
    public.answer_sources
from public, anon, authenticated;

revoke create on schema public from public, anon, authenticated;

-- Auth still inserts profiles through its existing security-definer trigger.
-- This function is not a browser RPC; keep its fixed, empty search_path.
revoke all privileges on function public.handle_new_user()
    from public, anon, authenticated;
grant execute on function public.handle_new_user() to supabase_auth_admin;

-- Avoid restoring client access when a later app migration adds a table.
-- Only postgres-created objects in public are affected by these statements.
alter default privileges for role postgres in schema public
    revoke all privileges on tables from public, anon, authenticated;
alter default privileges for role postgres in schema public
    revoke all privileges on sequences from public, anon, authenticated;
alter default privileges for role postgres in schema public
    revoke execute on functions from anon, authenticated;

-- PostgreSQL's implicit PUBLIC execute default is global, so a schema-only
-- REVOKE cannot override it. This affects FUTURE postgres-created functions in
-- all schemas, not existing functions. Grant intended callers explicitly.
alter default privileges for role postgres
    revoke execute on functions from public;

commit;
