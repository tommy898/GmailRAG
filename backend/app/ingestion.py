import uuid
from collections.abc import Mapping, Sequence

from app.chunking import CHUNKER_VERSION, chunk_email
from app.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    embed_texts,
)
#chunks and embeds one email(call from embedding.py)

def embedding_to_pgvector(embedding: Sequence[float]) -> str:#python float list to pgvector
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def require_email_value(email: Mapping[str, object], key: str) -> str:
    value = email.get(key)

    if not value:
        raise ValueError(f"email record is missing {key}")

    return str(value)

def ensure_profile(
    conn,
    profile_id: uuid.UUID,
    email: str,
    display_name: str | None = None,
) -> uuid.UUID:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            insert into profiles (id, email, display_name)
            values (%s, %s, %s)
            on conflict (id) do update set
                email = excluded.email,
                display_name = coalesce(excluded.display_name, profiles.display_name),
                updated_at = now()
            returning id
            """,
            (profile_id, email, display_name),
        )

        return cursor.fetchone()[0]


def ensure_gmail_account(
    conn,
    profile_id: uuid.UUID,
    gmail_address: str,
) -> uuid.UUID:
    with conn.cursor() as cursor:
        cursor.execute(
            """
            insert into gmail_accounts (
                profile_id,
                gmail_address,
                sync_status,
                last_synced_at
            )
            values (%s, %s, 'ready', now())
            on conflict (profile_id, gmail_address) do update set
                sync_status = 'ready',
                last_synced_at = now(),
                updated_at = now()
            returning id
            """,
            (profile_id, gmail_address),
        )

        return cursor.fetchone()[0]

#if exist, update, else insert
def upsert_email(
    conn,
    gmail_account_id: uuid.UUID,
    email: Mapping[str, object],
) -> uuid.UUID:
    gmail_message_id = require_email_value(email, "gmail_message_id")

    with conn.cursor() as cursor:
        cursor.execute(
            """
            insert into emails (
                gmail_account_id,
                gmail_message_id,
                gmail_thread_id,
                from_email,
                to_email,
                subject,
                gmail_date_raw,
                snippet,
                body_text
            )
            values (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            on conflict (gmail_account_id, gmail_message_id) do update set
                gmail_thread_id = excluded.gmail_thread_id,
                from_email = excluded.from_email,
                to_email = excluded.to_email,
                subject = excluded.subject,
                gmail_date_raw = excluded.gmail_date_raw,
                snippet = excluded.snippet,
                body_text = excluded.body_text,
                updated_at = now()
            returning id
            """,
            (
                gmail_account_id,
                gmail_message_id,
                email.get("gmail_thread_id"),
                email.get("from_email"),
                email.get("to_email"),
                email.get("subject"),
                email.get("gmail_date_raw"),
                email.get("snippet"),
                email.get("body_text"),
            ),
        )

        return cursor.fetchone()[0]


def replace_chunks_and_embeddings_for_email(
    conn,
    email_id: uuid.UUID,
    email: Mapping[str, object],
    embed_chunks: bool = True,
) -> int:
    chunks = chunk_email(email)

    with conn.cursor() as cursor:
        cursor.execute(
            """
            delete from email_chunks
            where email_id = %s
              and chunker_version = %s
            """,
            (email_id, CHUNKER_VERSION),
        )

    chunk_ids = []

    for chunk_index, chunk in enumerate(chunks):
        with conn.cursor() as cursor:
            cursor.execute(
                """
                insert into email_chunks (
                    email_id,
                    chunk_index,
                    text,
                    character_count,
                    token_count,
                    chunker_version
                )
                values (%s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    email_id,
                    chunk_index,
                    chunk,
                    len(chunk),
                    None,
                    CHUNKER_VERSION,
                ),
            )

            chunk_ids.append(cursor.fetchone()[0])

    if embed_chunks and chunks:
        embeddings = embed_texts(chunks)

        for chunk_id, embedding in zip(chunk_ids, embeddings, strict=True):
            upsert_embedding(conn, chunk_id, embedding)

    return len(chunks)


def upsert_embedding(
    conn,
    chunk_id: uuid.UUID,
    embedding: Sequence[float],
) -> uuid.UUID:
    if len(embedding) != EMBEDDING_DIMENSION:
        raise ValueError(
            f"expected {EMBEDDING_DIMENSION} embedding values, got {len(embedding)}"
        )

    with conn.cursor() as cursor:
        cursor.execute(
            """
            insert into email_embeddings (
                chunk_id,
                embedding,
                embedding_model,
                embedding_dimension
            )
            values (%s, %s::vector, %s, %s)
            on conflict (chunk_id, embedding_model) do update set
                embedding = excluded.embedding,
                embedding_dimension = excluded.embedding_dimension,
                created_at = now()
            returning id
            """,
            (
                chunk_id,
                embedding_to_pgvector(embedding),
                EMBEDDING_MODEL,
                EMBEDDING_DIMENSION,
            ),
        )

        return cursor.fetchone()[0]
