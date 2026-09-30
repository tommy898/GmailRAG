from collections.abc import Sequence

import psycopg

from app.config import get_required_environment_variable


def embedding_to_pgvector(embedding: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in embedding) + "]"


def get_database_url():
    return get_required_environment_variable("DATABASE_URL")


def get_connection():
    return psycopg.connect(get_database_url())


def fetch_database_time():
    with get_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute("select now();")
            return cursor.fetchone()[0]
