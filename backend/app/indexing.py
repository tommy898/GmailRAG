import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from app.chunking import CHUNKER_VERSION, chunk_email
from app.db import embedding_to_pgvector
from app.embeddings import (
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    embed_texts,
)


@dataclass(frozen=True)
class StoredChunk:
    id: uuid.UUID
    text: str


def replace_email_chunks(
    conn,
    email_id: uuid.UUID,
    email: Mapping[str, object],
) -> list[StoredChunk]:
    chunks = chunk_email(email)
    stored_chunks = []

    with conn.cursor() as cursor:
        cursor.execute(
            """
            delete from email_chunks
            where email_id = %s
            """,
            (email_id,),
        )

        for chunk_index, chunk in enumerate(chunks):
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

            stored_chunks.append(
                StoredChunk(
                    id=cursor.fetchone()[0],
                    text=chunk,
                )
            )

    return stored_chunks


def embed_and_store_chunks(
    conn,
    chunks: Sequence[StoredChunk],
) -> int:
    if not chunks:
        return 0

    embeddings = embed_texts([chunk.text for chunk in chunks])

    for chunk, embedding in zip(chunks, embeddings, strict=True):
        upsert_embedding(conn, chunk.id, embedding)

    return len(embeddings)


def index_email(
    conn,
    email_id: uuid.UUID,
    email: Mapping[str, object],
    embed_chunks: bool = True,
) -> int:
    stored_chunks = replace_email_chunks(conn, email_id, email)

    if embed_chunks:
        embed_and_store_chunks(conn, stored_chunks)

    return len(stored_chunks)


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
