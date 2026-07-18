from app.db import get_connection
from app.embeddings import EMBEDDING_MODEL, embed_text
from app.ingestion import embedding_to_pgvector

def retrieve_chunks(question: str, limit: int = 20) -> list[dict]:  #20 candidates
    query_embedding = embed_text(question)
    query_vector = embedding_to_pgvector(query_embedding)
    #L2 distance
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                select
                    c.id as chunk_id,
                    c.text,
                    c.chunk_index,
                    e.subject,
                    e.from_email,
                    e.gmail_date_raw,
                    ee.embedding <-> %s::vector as distance
                from email_embeddings ee
                join email_chunks c on c.id = ee.chunk_id
                join emails e on e.id = c.email_id
                where ee.embedding_model = %s
                order by ee.embedding <-> %s::vector
                limit %s
                """,
                (
                    query_vector,
                    EMBEDDING_MODEL,
                    query_vector,
                    limit,
                ),
            )

            rows = cursor.fetchall()

    candidates = []

    for row in rows:
        candidates.append(
            {
                "chunk_id": str(row[0]),
                "text": row[1],
                "chunk_index": row[2],
                "subject": row[3],
                "from_email": row[4],
                "date": row[5],
                "distance": float(row[6]),

            }
        )
    return candidates
            