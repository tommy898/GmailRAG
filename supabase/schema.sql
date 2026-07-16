create extension if not exists vector;
create extension if not exists pgcrypto;

create table if not exists profiles (
    id uuid primary key,
    email text not null,
    display_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists gmail_accounts (
    id uuid primary key default gen_random_uuid(),
    profile_id uuid not null references profiles(id) on delete cascade,
    gmail_address text not null,
    google_account_id text,
    access_token_encrypted text,
    refresh_token_encrypted text,
    token_expires_at timestamptz,
    scope text,
    last_history_id text,
    last_synced_at timestamptz,
    sync_status text not null default 'not_synced',
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (profile_id, gmail_address),
    check (sync_status in ('not_synced', 'syncing', 'ready', 'failed'))
);

create table if not exists emails (
    id uuid primary key default gen_random_uuid(),
    gmail_account_id uuid not null references gmail_accounts(id) on delete cascade,
    gmail_message_id text not null,
    gmail_thread_id text,
    from_email text,
    to_email text,
    subject text,
    sent_at timestamptz,
    gmail_date_raw text,
    snippet text,
    body_text text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (gmail_account_id, gmail_message_id)
);

create table if not exists email_chunks (
    id uuid primary key default gen_random_uuid(),
    email_id uuid not null references emails(id) on delete cascade,
    chunk_index integer not null,
    text text not null,
    character_count integer,
    token_count integer,
    chunker_version text not null,
    created_at timestamptz not null default now(),
    unique (email_id, chunk_index, chunker_version)
);

create table if not exists email_embeddings (
    id uuid primary key default gen_random_uuid(),
    chunk_id uuid not null references email_chunks(id) on delete cascade,
    embedding vector(384) not null,
    embedding_model text not null,
    embedding_dimension integer not null default 384,
    created_at timestamptz not null default now(),
    unique (chunk_id, embedding_model),
    check (embedding_dimension = 384)
);

create table if not exists sync_jobs (
    id uuid primary key default gen_random_uuid(),
    gmail_account_id uuid not null references gmail_accounts(id) on delete cascade,
    job_type text not null,
    status text not null default 'pending',
    started_at timestamptz,
    finished_at timestamptz,
    error_message text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    check (job_type in ('gmail_sync', 'chunk_emails', 'embed_chunks', 'full_reindex')),
    check (status in ('pending', 'running', 'done', 'failed'))
);

create table if not exists queries (
    id uuid primary key default gen_random_uuid(),
    profile_id uuid not null references profiles(id) on delete cascade,
    gmail_account_id uuid references gmail_accounts(id) on delete set null,
    question text not null,
    created_at timestamptz not null default now()
);

create table if not exists answers (
    id uuid primary key default gen_random_uuid(),
    query_id uuid not null references queries(id) on delete cascade,
    answer_text text not null,
    generation_model text not null,
    created_at timestamptz not null default now()
);

create table if not exists answer_sources (
    id uuid primary key default gen_random_uuid(),
    answer_id uuid not null references answers(id) on delete cascade,
    chunk_id uuid not null references email_chunks(id) on delete cascade,
    source_rank integer not null,
    retrieval_distance double precision,
    rerank_score double precision,
    created_at timestamptz not null default now(),
    unique (answer_id, source_rank),
    unique (answer_id, chunk_id)
);

create index if not exists gmail_accounts_profile_id_idx
    on gmail_accounts(profile_id);

create index if not exists emails_gmail_account_id_idx
    on emails(gmail_account_id);

create index if not exists emails_gmail_account_message_idx
    on emails(gmail_account_id, gmail_message_id);

create index if not exists emails_sent_at_idx
    on emails(sent_at);

create index if not exists email_chunks_email_id_idx
    on email_chunks(email_id);

create index if not exists email_embeddings_chunk_id_idx
    on email_embeddings(chunk_id);

create index if not exists sync_jobs_status_created_at_idx
    on sync_jobs(status, created_at);

create index if not exists queries_profile_created_at_idx
    on queries(profile_id, created_at desc);

create index if not exists answers_query_id_idx
    on answers(query_id);

create index if not exists answer_sources_answer_id_idx
    on answer_sources(answer_id);

create index if not exists email_embeddings_embedding_hnsw_idx
    on email_embeddings
    using hnsw (embedding vector_l2_ops);

alter table profiles enable row level security;
alter table gmail_accounts enable row level security;
alter table emails enable row level security;
alter table email_chunks enable row level security;
alter table email_embeddings enable row level security;
alter table sync_jobs enable row level security;
alter table queries enable row level security;
alter table answers enable row level security;
alter table answer_sources enable row level security;
